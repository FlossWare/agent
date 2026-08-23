"""CodingAgent: The main orchestration loop.

    task -> (optional worktree) -> worker -> hard gates -> arbiter
         -> accept/reject -> retry -> apply diff / commit

Deterministic verification always overrides LLM acceptance decisions.
"""

from __future__ import annotations

import logging
from typing import Any

from personal_agent.arbiter import Arbiter
from personal_agent.repo import Repo
from personal_agent.router import create_free_router
from personal_agent.security import redact_secrets
from personal_agent.types import (
    ArbiterDecision,
    ArbiterFinding,
    Decision,
    Task,
    TaskResult,
    WorkerResult,
)
from personal_agent.verification import (
    VerificationConfig,
    VerificationEvidence,
    evaluate_hard_gates,
)
from personal_agent.worker import Worker

logger = logging.getLogger(__name__)


def _decision_from_evidence(evidence: VerificationEvidence) -> ArbiterDecision:
    return ArbiterDecision(
        decision=Decision.REJECT,
        confidence=1.0,
        reason="Hard verification gate failed: " + "; ".join(evidence.reasons),
        findings=[
            ArbiterFinding(severity="critical", description=r)
            for r in evidence.reasons
        ],
        required_changes=[
            "Fix failing tests, policy violations, or syntax errors before acceptance"
        ],
        model_used="hard-gate",
    )


class CodingAgent:
    """Orchestrates the worker/arbiter loop for coding tasks."""

    def __init__(
        self,
        repo_path: str,
        *,
        router: Any | None = None,
        max_iterations: int = 3,
        use_worktree: bool = True,
        verification: VerificationConfig | None = None,
    ) -> None:
        self._primary_repo = Repo(repo_path)
        self._router = router or create_free_router()
        self._max_iterations = max_iterations
        self._use_worktree = use_worktree
        self._verification = verification or VerificationConfig()

    async def run(self, task: Task) -> TaskResult:
        """Execute the full worker/arbiter loop."""
        max_iter = task.max_iterations or self._max_iterations
        task.repo_path = str(self._primary_repo.path)

        # Optional required checks from task.commands (e.g. pytest)
        cfg = VerificationConfig(
            check_commands=self._verification.check_commands,
            check_policy_blocks=self._verification.check_policy_blocks,
            check_path_escapes=self._verification.check_path_escapes,
            check_python_syntax=self._verification.check_python_syntax,
            required_command_substrings=list(
                self._verification.required_command_substrings
            ),
        )
        # If the task specifies commands, require each to appear in successes
        # only when the user asked for them as gates — we treat task.commands
        # as commands to run, not as required substrings unless configured.

        work_repo = self._primary_repo
        isolated = False
        if self._use_worktree:
            try:
                work_repo = self._primary_repo.create_worktree()
                isolated = True
                logger.info("Using isolated worktree at %s", work_repo.path)
            except Exception as e:
                logger.warning(
                    "Worktree creation failed (%s); falling back to primary tree",
                    e,
                )
                work_repo = self._primary_repo
                isolated = False

        worker = Worker(self._router, work_repo)
        arbiter = Arbiter(self._router, work_repo)

        worker_results: list[WorkerResult] = []
        arbiter_decisions: list[ArbiterDecision] = []

        logger.info("Starting task: %s", task.description[:100])

        try:
            await self._router.initialize()
        except Exception:
            pass

        try:
            for iteration in range(1, max_iter + 1):
                logger.info("Iteration %d/%d", iteration, max_iter)

                if iteration == 1:
                    worker_result = await worker.investigate(task)
                else:
                    feedback = arbiter.format_feedback(arbiter_decisions[-1])
                    worker_result = await worker.fix(
                        task, feedback, worker_results[-1]
                    )

                worker_results.append(worker_result)
                self._log_worker_result(worker_result, iteration)

                evidence = evaluate_hard_gates(
                    worker_result,
                    workspace=work_repo.path,
                    config=cfg,
                )
                if not evidence.passed:
                    decision = _decision_from_evidence(evidence)
                    arbiter_decisions.append(decision)
                    self._log_arbiter_decision(decision, iteration)
                    if iteration == max_iter:
                        break
                    continue

                arbiter_decision = await arbiter.review(task, worker_result)
                arbiter_decisions.append(arbiter_decision)
                self._log_arbiter_decision(arbiter_decision, iteration)

                if arbiter_decision.decision == Decision.ACCEPT:
                    logger.info("Task ACCEPTED on iteration %d", iteration)
                    break

                if iteration == max_iter:
                    logger.warning(
                        "Max iterations (%d) reached without acceptance", max_iter
                    )

            final_diff = work_repo.git_diff()
            commit_msg = self._generate_commit_message(task, arbiter_decisions)

            accepted = (
                arbiter_decisions
                and arbiter_decisions[-1].decision == Decision.ACCEPT
            )

            if isolated and accepted and final_diff.strip():
                apply_result = work_repo.apply_diff_to(self._primary_repo)
                if apply_result.returncode != 0:
                    logger.error(
                        "Failed to apply accepted diff to primary tree: %s",
                        apply_result.stderr,
                    )
                    arbiter_decisions[-1] = ArbiterDecision(
                        decision=Decision.REJECT,
                        confidence=1.0,
                        reason=(
                            "Accepted in worktree but failed to apply to primary: "
                            + (apply_result.stderr or apply_result.stdout)
                        ),
                        model_used="apply-gate",
                    )

            return TaskResult(
                task=task,
                decision=(
                    arbiter_decisions[-1].decision
                    if arbiter_decisions
                    else Decision.REJECT
                ),
                iterations=len(worker_results),
                worker_results=worker_results,
                arbiter_decisions=arbiter_decisions,
                final_diff=final_diff,
                commit_message=commit_msg,
            )
        finally:
            if isolated:
                try:
                    work_repo.cleanup_worktree()
                except Exception as e:
                    logger.warning("Worktree cleanup failed: %s", e)

    async def investigate_only(self, task: Task) -> WorkerResult:
        try:
            await self._router.initialize()
        except Exception:
            pass
        worker = Worker(self._router, self._primary_repo)
        return await worker.investigate(task)

    async def review_only(
        self, task: Task, worker_result: WorkerResult
    ) -> ArbiterDecision:
        try:
            await self._router.initialize()
        except Exception:
            pass
        evidence = evaluate_hard_gates(
            worker_result,
            workspace=self._primary_repo.path,
            config=self._verification,
        )
        if not evidence.passed:
            return _decision_from_evidence(evidence)
        arbiter = Arbiter(self._router, self._primary_repo)
        return await arbiter.review(task, worker_result)

    def _generate_commit_message(
        self, task: Task, decisions: list[ArbiterDecision]
    ) -> str:
        summary = task.description
        if len(summary) > 72:
            summary = summary[:69] + "..."

        parts = [summary, ""]
        if decisions:
            last = decisions[-1]
            parts.append(
                f"Arbiter: {last.decision.value} (confidence: {last.confidence:.0%})"
            )
            if last.reason:
                parts.append(f"Reason: {redact_secrets(last.reason)}")

        parts.append("")
        parts.append(f"Iterations: {len(decisions)}")
        if decisions and decisions[-1].model_used:
            parts.append(f"Model: {decisions[-1].model_used}")

        return "\n".join(parts)

    def _log_worker_result(self, result: WorkerResult, iteration: int) -> None:
        logger.info(
            "  Worker (iter %d): plan=%s, changes=%d, tests=%d",
            iteration,
            (result.plan[:80] if result.plan else "(none)"),
            len(result.changes),
            len(result.test_results),
        )
        for tr in result.test_results:
            status = "PASS" if tr.success else "FAIL"
            logger.info("    [%s] %s", status, tr.command)

    def _log_arbiter_decision(
        self, decision: ArbiterDecision, iteration: int
    ) -> None:
        logger.info(
            "  Arbiter (iter %d): %s (confidence=%.0f%%, findings=%d)",
            iteration,
            decision.decision.value.upper(),
            decision.confidence * 100,
            len(decision.findings),
        )
        if decision.decision == Decision.REJECT:
            logger.info("    Reason: %s", redact_secrets(decision.reason[:200]))
