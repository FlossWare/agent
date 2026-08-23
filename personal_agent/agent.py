"""CodingAgent: The main orchestration loop.

    task -> (optional worktree) -> worker -> test -> hard gates -> arbiter
         -> accept/reject -> retry -> apply diff / commit

Deterministic verification (test failures, policy violations) always
overrides LLM acceptance decisions.
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
from personal_agent.worker import Worker

logger = logging.getLogger(__name__)


def _hard_gate_failures(worker_result: WorkerResult) -> list[str]:
    """Return reasons that must force REJECT regardless of LLM judgment."""
    reasons: list[str] = []
    for tr in worker_result.test_results:
        if tr.returncode != 0:
            # Distinguish policy blocks from ordinary test failures
            if "Blocked by security policy" in (tr.stderr or ""):
                reasons.append(f"Security policy violation: {tr.command}")
            else:
                reasons.append(
                    f"Command failed (exit {tr.returncode}): {tr.command}"
                )
    for change in worker_result.changes:
        # apply_changes records policy failures as CommandResult in some paths;
        # path escapes raise and are already reflected if apply returned errors.
        pass
    return reasons


class CodingAgent:
    """Orchestrates the worker/arbiter loop for coding tasks.

    Usage::

        agent = CodingAgent("/path/to/repo")
        result = await agent.run(Task(
            description="Fix the bug in auth.py",
            repo_path="/path/to/repo",
        ))

        if result.decision == Decision.ACCEPT:
            print("Changes accepted!")
            print(result.final_diff)
    """

    def __init__(
        self,
        repo_path: str,
        *,
        router: Any | None = None,
        max_iterations: int = 3,
        use_worktree: bool = True,
    ) -> None:
        self._primary_repo = Repo(repo_path)
        self._router = router or create_free_router()
        self._max_iterations = max_iterations
        self._use_worktree = use_worktree

    async def run(self, task: Task) -> TaskResult:
        """Execute the full worker/arbiter loop."""
        max_iter = task.max_iterations or self._max_iterations
        task.repo_path = str(self._primary_repo.path)

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

                # Deterministic hard gates — always authoritative (issue #5)
                gate_failures = _hard_gate_failures(worker_result)
                if gate_failures:
                    decision = ArbiterDecision(
                        decision=Decision.REJECT,
                        confidence=1.0,
                        reason=(
                            "Hard verification gate failed: "
                            + "; ".join(gate_failures)
                        ),
                        findings=[
                            ArbiterFinding(
                                severity="critical",
                                description=r,
                            )
                            for r in gate_failures
                        ],
                        required_changes=[
                            "Fix failing tests / remove policy-violating commands"
                        ],
                        model_used="hard-gate",
                    )
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

            # Explicit apply step when using an isolated worktree
            if isolated and accepted and final_diff.strip():
                apply_result = work_repo.apply_diff_to(self._primary_repo)
                if apply_result.returncode != 0:
                    logger.error(
                        "Failed to apply accepted diff to primary tree: %s",
                        apply_result.stderr,
                    )
                    # Downgrade to reject if apply failed
                    arbiter_decisions[-1] = ArbiterDecision(
                        decision=Decision.REJECT,
                        confidence=1.0,
                        reason=(
                            "Accepted in worktree but failed to apply to primary: "
                            + (apply_result.stderr or apply_result.stdout)
                        ),
                        model_used="apply-gate",
                    )
                    accepted = False

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
        """Run investigation without the arbiter loop."""
        try:
            await self._router.initialize()
        except Exception:
            pass
        worker = Worker(self._router, self._primary_repo)
        return await worker.investigate(task)

    async def review_only(
        self, task: Task, worker_result: WorkerResult
    ) -> ArbiterDecision:
        """Run arbiter review on existing worker results."""
        try:
            await self._router.initialize()
        except Exception:
            pass
        arbiter = Arbiter(self._router, self._primary_repo)
        gates = _hard_gate_failures(worker_result)
        if gates:
            return ArbiterDecision(
                decision=Decision.REJECT,
                confidence=1.0,
                reason="Hard verification gate failed: " + "; ".join(gates),
                findings=[
                    ArbiterFinding(severity="critical", description=r) for r in gates
                ],
                model_used="hard-gate",
            )
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
