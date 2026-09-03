"""Arbiter: independent review of worker results with verification gates."""

from __future__ import annotations

import json
import logging
from typing import Any

from personal_agent.repo import Repo
from personal_agent.security import redact_secrets
from personal_agent.types import (
    ArbiterDecision,
    ArbiterFinding,
    Decision,
    Task,
    WorkerResult,
)

logger = logging.getLogger(__name__)

ARBITER_SCHEMA = {
    "type": "object",
    "required": ["decision", "confidence", "reason"],
    "properties": {
        "decision": {"type": "string", "enum": ["accept", "reject"]},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "reason": {"type": "string"},
        "findings": {"type": "array"},
        "required_changes": {"type": "array", "items": {"type": "string"}},
    },
}

REVIEW_PROMPT = """You are an independent code reviewer. You were NOT involved in writing this code.

ORIGINAL TASK:
{task_description}

WORKER'S PLAN:
{plan}

WORKER'S FINDINGS:
{findings}

CHANGES MADE (diff):
{diff}

TEST RESULTS:
{test_results}

CURRENT REPOSITORY STATE:
{tree}

{changed_files}

Review the worker's changes against the original task. Be rigorous but fair.

Respond with a JSON object:
{{
    "decision": "accept" or "reject",
    "confidence": 0.0 to 1.0,
    "reason": "Clear explanation of your decision",
    "findings": [
        {{
            "severity": "critical|high|medium|low",
            "description": "What the issue is",
            "file": "path/to/file.py",
            "suggestion": "How to fix it"
        }}
    ],
    "required_changes": ["Specific change required before acceptance"]
}}

Decision criteria:
- ACCEPT if changes correctly address the task and tests pass
- REJECT if there are correctness issues, missing test coverage, or the task is not properly addressed
- A few LOW/MEDIUM findings with passing tests can still be ACCEPTED
- Any CRITICAL finding requires REJECT
- You cannot override failed tests or security policy violations
"""


class _RouterBackend:
    """Adapt the agent router to evaluation-ai's LLMBackend protocol."""

    def __init__(self, router: Any) -> None:
        self._router = router

    async def chat(
        self, messages: list[Any], *, model: str = "", **kwargs: Any
    ) -> Any:
        return await self._router.chat(messages, model=model or None, **kwargs)


class Arbiter:
    """Review worker results and require independent verification when available."""

    def __init__(
        self,
        router: Any,
        repo: Repo,
        *,
        verification_panel_size: int = 3,
        require_independent_verification: bool = False,
    ) -> None:
        self._router = router
        self._repo = repo
        self._verification_panel_size = verification_panel_size
        self._require_independent_verification = require_independent_verification

    async def review(self, task: Task, worker_result: WorkerResult) -> ArbiterDecision:
        decision = await self._review_with_llm(task, worker_result)
        verification = await self._independent_verification(task, worker_result)
        if verification is None:
            if self._require_independent_verification:
                return ArbiterDecision(
                    decision=Decision.REJECT,
                    confidence=0.0,
                    reason="Independent verification is required but evaluation-ai is unavailable or no panel exists.",
                    findings=[
                        ArbiterFinding(
                            severity="critical",
                            description="No independent verification panel was available.",
                        )
                    ],
                    required_changes=[
                        "Install/configure evaluation-ai with at least two independent models."
                    ],
                    model_used=decision.model_used,
                )
            return decision

        verdict, confidence, panel_models = verification
        if verdict != "CONFIRMED":
            return ArbiterDecision(
                decision=Decision.REJECT,
                confidence=confidence,
                reason=(
                    f"Independent verification returned {verdict}; "
                    "the worker result is not safe to accept."
                ),
                findings=[
                    ArbiterFinding(
                        severity="high" if verdict == "UNCERTAIN" else "critical",
                        description=f"Adversarial verification verdict: {verdict}.",
                    )
                ],
                required_changes=[
                    "Address independent verification findings before acceptance."
                ],
                model_used=decision.model_used,
            )

        if decision.decision != Decision.ACCEPT:
            return decision
        return ArbiterDecision(
            decision=Decision.ACCEPT,
            confidence=min(decision.confidence, confidence),
            reason=(
                decision.reason
                + f" Independent verification confirmed by {len(panel_models)} panel models."
            ),
            findings=decision.findings,
            required_changes=decision.required_changes,
            model_used=decision.model_used,
        )

    async def _review_with_llm(
        self, task: Task, worker_result: WorkerResult
    ) -> ArbiterDecision:
        diff = redact_secrets(self._repo.git_diff())
        tree = self._repo.tree(max_depth=2)
        test_summary = "\n".join(
            f"$ {r.command}\n  exit={r.returncode}\n  "
            f"{redact_secrets(r.stdout[:500])}\n  {redact_secrets(r.stderr[:500])}"
            for r in worker_result.test_results
        ) or "(no tests run)"
        changed_files = ""
        for change in worker_result.changes:
            try:
                content = self._repo.read_file(change.path)
                changed_files += (
                    f"\n=== {change.path} (after change) ===\n"
                    f"{redact_secrets(content[:5000])}\n"
                )
            except Exception:
                continue
        findings_text = (
            "\n".join(f"- {redact_secrets(f)}" for f in worker_result.findings)
            or "(none)"
        )
        prompt = REVIEW_PROMPT.format(
            task_description=task.description,
            plan=redact_secrets(worker_result.plan),
            findings=findings_text,
            diff=diff or "(no diff - no changes made)",
            test_results=test_summary,
            tree=tree,
            changed_files=changed_files,
        )
        resp = await self._router.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=4096,
        )
        return self._parse_decision(resp)

    async def _independent_verification(
        self, task: Task, worker_result: WorkerResult
    ) -> tuple[str, float, list[str]] | None:
        try:
            from evaluation_ai import AdversarialVerifier
        except ImportError:
            return None
        try:
            models = await self._router.list_models()
        except (AttributeError, TypeError, RuntimeError):
            return None

        model_ids = sorted(
            {
                str(m.model_id)
                for m in models
                if getattr(m, "model_id", None)
            }
        )
        if len(model_ids) < 2:
            return None

        verifier = AdversarialVerifier(
            backend=_RouterBackend(self._router),
            available_models=model_ids,
            panel_size=self._verification_panel_size,
        )
        result = await verifier.verify(
            self._verification_candidate(worker_result),
            task=task.description,
            candidate_model=worker_result.model_used,
        )

        verdict = result.verdict
        confidence = result.confidence
        try:
            from consensus_ai import ChatResponse, MajorityVoteStrategy

            votes = [
                ChatResponse(
                    content=item.verdict,
                    model=item.model,
                    provider="evaluation-ai",
                )
                for item in result.panel_results
            ]
            if votes:
                outcome = MajorityVoteStrategy().select(votes)
                verdict = outcome.selected.content
                selected_index = next(
                    i
                    for i, item in enumerate(votes)
                    if item.model == outcome.selected.model
                )
                confidence = outcome.scores[selected_index]
        except (ImportError, AttributeError, TypeError, KeyError, StopIteration):
            logger.debug(
                "Consensus aggregation unavailable; using evaluation result"
            )
        return verdict, confidence, result.panel_models

    @staticmethod
    def _verification_candidate(worker_result: WorkerResult) -> str:
        return json.dumps(
            {
                "plan": worker_result.plan,
                "findings": worker_result.findings,
                "changes": [
                    {"path": c.path, "action": c.action, "content": c.content}
                    for c in worker_result.changes
                ],
                "tests": [
                    {"command": r.command, "returncode": r.returncode}
                    for r in worker_result.test_results
                ],
            },
            indent=2,
        )

    def _parse_decision(self, resp: Any) -> ArbiterDecision:
        text = resp.content.strip()
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0]
        elif "```" in text:
            text = text.split("```", 1)[1].split("```", 1)[0]
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start:end])
                return ArbiterDecision(
                    decision=Decision(data.get("decision", "reject")),
                    confidence=max(
                        0.0, min(1.0, float(data.get("confidence", 0.0)))
                    ),
                    reason=data.get("reason", ""),
                    findings=[
                        ArbiterFinding(
                            severity=f.get("severity", "medium"),
                            description=f.get("description", ""),
                            file=f.get("file", ""),
                            suggestion=f.get("suggestion", ""),
                        )
                        for f in data.get("findings", [])
                    ],
                    required_changes=data.get("required_changes", []),
                    model_used=getattr(resp, "model", ""),
                )
            except (json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
                logger.warning("Failed to parse arbiter response: %s", exc)
        return ArbiterDecision(
            decision=Decision.REJECT,
            confidence=0.0,
            reason=f"Failed to parse arbiter response. Raw: {resp.content[:500]}",
            model_used=getattr(resp, "model", ""),
        )

    def format_feedback(self, decision: ArbiterDecision) -> str:
        parts = [
            f"DECISION: {decision.decision.value.upper()}",
            f"REASON: {redact_secrets(decision.reason)}",
        ]
        if decision.findings:
            parts.append("\nFINDINGS:")
            for finding in decision.findings:
                parts.append(
                    f"  [{finding.severity.upper()}] "
                    f"{redact_secrets(finding.description)}"
                    + (f" (in {finding.file})" if finding.file else "")
                    + (
                        f"\n    Suggestion: {redact_secrets(finding.suggestion)}"
                        if finding.suggestion
                        else ""
                    )
                )
        if decision.required_changes:
            parts.append("\nREQUIRED CHANGES:")
            for change in decision.required_changes:
                parts.append(f"  - {redact_secrets(change)}")
        return "\n".join(parts)
