"""Arbiter: Independent review of worker results with structured decisions.

Receives the original task, worker's plan/result, diff, and test results.
Returns a structured ArbiterDecision (accept/reject with findings).

Secrets are redacted from prompts and feedback. Deterministic hard gates
are enforced by CodingAgent before this reviewer is consulted.
"""

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
        "decision": {
            "type": "string",
            "enum": ["accept", "reject"],
        },
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
        },
        "reason": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "high", "medium", "low"],
                    },
                    "description": {"type": "string"},
                    "file": {"type": "string"},
                    "suggestion": {"type": "string"},
                },
            },
        },
        "required_changes": {
            "type": "array",
            "items": {"type": "string"},
        },
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
    "required_changes": [
        "Specific change that must be made before acceptance"
    ]
}}

Decision criteria:
- ACCEPT if changes correctly address the task and tests pass
- REJECT if there are correctness issues, missing test coverage, or the task is not properly addressed
- A few LOW/MEDIUM findings with passing tests can still be ACCEPTED
- Any CRITICAL finding requires REJECT
- You cannot override failed tests or security policy violations; those are handled separately
"""


class Arbiter:
    """Reviews worker results and issues structured decisions.

    Uses a DIFFERENT model call than the worker (when possible)
    to provide independent review.
    """

    def __init__(self, router: Any, repo: Repo) -> None:
        self._router = router
        self._repo = repo

    async def review(self, task: Task, worker_result: WorkerResult) -> ArbiterDecision:
        """Review worker's changes and return a structured decision."""
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

        findings_text = "\n".join(
            f"- {redact_secrets(f)}" for f in worker_result.findings
        ) or "(none)"

        prompt = REVIEW_PROMPT.format(
            task_description=task.description,
            plan=redact_secrets(worker_result.plan),
            findings=findings_text,
            diff=diff or "(no diff — no changes made)",
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

    def _parse_decision(self, resp: Any) -> ArbiterDecision:
        """Parse LLM response into a structured ArbiterDecision."""
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
                    confidence=float(data.get("confidence", 0.0)),
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
            except (json.JSONDecodeError, ValueError, KeyError) as e:
                logger.warning("Failed to parse arbiter response: %s", e)

        return ArbiterDecision(
            decision=Decision.REJECT,
            confidence=0.0,
            reason=f"Failed to parse arbiter response. Raw: {resp.content[:500]}",
            model_used=getattr(resp, "model", ""),
        )

    def format_feedback(self, decision: ArbiterDecision) -> str:
        """Format arbiter decision as actionable feedback for workers."""
        parts = [f"DECISION: {decision.decision.value.upper()}"]
        parts.append(f"REASON: {redact_secrets(decision.reason)}")

        if decision.findings:
            parts.append("\nFINDINGS:")
            for f in decision.findings:
                parts.append(
                    f"  [{f.severity.upper()}] {redact_secrets(f.description)}"
                    + (f" (in {f.file})" if f.file else "")
                    + (
                        f"\n    Suggestion: {redact_secrets(f.suggestion)}"
                        if f.suggestion
                        else ""
                    )
                )

        if decision.required_changes:
            parts.append("\nREQUIRED CHANGES:")
            for c in decision.required_changes:
                parts.append(f"  - {redact_secrets(c)}")

        return "\n".join(parts)
