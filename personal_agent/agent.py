"""CodingAgent: The main orchestration loop.

    task -> worker -> test -> arbiter -> accept/reject -> retry -> commit/PR
"""

from __future__ import annotations

import logging
from typing import Any

from personal_agent.arbiter import Arbiter
from personal_agent.repo import Repo
from personal_agent.router import create_free_router
from personal_agent.types import (
    ArbiterDecision,
    Decision,
    Task,
    TaskResult,
    WorkerResult,
)
from personal_agent.worker import Worker

logger = logging.getLogger(__name__)


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
    ) -> None:
        self._repo = Repo(repo_path)
        self._router = router or create_free_router()
        self._max_iterations = max_iterations
        self._worker = Worker(self._router, self._repo)
        self._arbiter = Arbiter(self._router, self._repo)

    async def run(self, task: Task) -> TaskResult:
        """Execute the full worker/arbiter loop."""
        max_iter = task.max_iterations or self._max_iterations
        task.repo_path = str(self._repo.path)

        worker_results: list[WorkerResult] = []
        arbiter_decisions: list[ArbiterDecision] = []

        logger.info("Starting task: %s", task.description[:100])

        try:
            await self._router.initialize()
        except Exception:
            pass

        for iteration in range(1, max_iter + 1):
            logger.info("Iteration %d/%d", iteration, max_iter)

            if iteration == 1:
                worker_result = await self._worker.investigate(task)
            else:
                feedback = self._arbiter.format_feedback(arbiter_decisions[-1])
                worker_result = await self._worker.fix(
                    task, feedback, worker_results[-1]
                )

            worker_results.append(worker_result)

            self._log_worker_result(worker_result, iteration)

            arbiter_decision = await self._arbiter.review(task, worker_result)
            arbiter_decisions.append(arbiter_decision)

            self._log_arbiter_decision(arbiter_decision, iteration)

            if arbiter_decision.decision == Decision.ACCEPT:
                logger.info("Task ACCEPTED on iteration %d", iteration)
                break

            if iteration == max_iter:
                logger.warning(
                    "Max iterations (%d) reached without acceptance", max_iter
                )

        final_diff = self._repo.git_diff()
        commit_msg = self._generate_commit_message(task, arbiter_decisions)

        return TaskResult(
            task=task,
            decision=arbiter_decisions[-1].decision if arbiter_decisions else Decision.REJECT,
            iterations=len(worker_results),
            worker_results=worker_results,
            arbiter_decisions=arbiter_decisions,
            final_diff=final_diff,
            commit_message=commit_msg,
        )

    async def investigate_only(self, task: Task) -> WorkerResult:
        """Run investigation without the arbiter loop."""
        try:
            await self._router.initialize()
        except Exception:
            pass
        return await self._worker.investigate(task)

    async def review_only(self, task: Task, worker_result: WorkerResult) -> ArbiterDecision:
        """Run arbiter review on existing worker results."""
        try:
            await self._router.initialize()
        except Exception:
            pass
        return await self._arbiter.review(task, worker_result)

    def _generate_commit_message(
        self, task: Task, decisions: list[ArbiterDecision]
    ) -> str:
        summary = task.description
        if len(summary) > 72:
            summary = summary[:69] + "..."

        parts = [summary, ""]
        if decisions:
            last = decisions[-1]
            parts.append(f"Arbiter: {last.decision.value} (confidence: {last.confidence:.0%})")
            if last.reason:
                parts.append(f"Reason: {last.reason}")

        parts.append("")
        parts.append(f"Iterations: {len(decisions)}")
        if decisions and decisions[-1].model_used:
            parts.append(f"Model: {decisions[-1].model_used}")

        return "\n".join(parts)

    def _log_worker_result(self, result: WorkerResult, iteration: int) -> None:
        logger.info(
            "  Worker (iter %d): plan=%s, changes=%d, tests=%d",
            iteration,
            result.plan[:80] if result.plan else "(none)",
            len(result.changes),
            len(result.test_results),
        )
        for tr in result.test_results:
            status = "PASS" if tr.success else "FAIL"
            logger.info("    [%s] %s", status, tr.command)

    def _log_arbiter_decision(self, decision: ArbiterDecision, iteration: int) -> None:
        logger.info(
            "  Arbiter (iter %d): %s (confidence=%.0f%%, findings=%d)",
            iteration,
            decision.decision.value.upper(),
            decision.confidence * 100,
            len(decision.findings),
        )
        if decision.decision == Decision.REJECT:
            logger.info("    Reason: %s", decision.reason[:200])
