"""CodingAgent: worker/arbiter orchestration loop."""

from __future__ import annotations

import logging
from typing import Any

from personal_agent.arbiter import Arbiter
from personal_agent.repo import Repo
from personal_agent.router import create_router
from personal_agent.security import redact_secrets
from personal_agent.types import ArbiterDecision, ArbiterFinding, Decision, Task, TaskResult, WorkerResult
from personal_agent.verification import VerificationConfig, VerificationEvidence, evaluate_hard_gates
from personal_agent.worker import Worker

logger = logging.getLogger(__name__)


def _decision_from_evidence(evidence: VerificationEvidence) -> ArbiterDecision:
    return ArbiterDecision(
        decision=Decision.REJECT,
        confidence=1.0,
        reason="Hard verification gate failed: " + "; ".join(evidence.reasons),
        findings=[ArbiterFinding(severity="critical", description=r) for r in evidence.reasons],
        required_changes=["Fix failing tests, policy violations, or syntax errors before acceptance"],
        model_used="hard-gate",
    )


class CodingAgent:
    """Orchestrates the coding worker/arbiter loop for a repository."""

    def __init__(self, repo_path: str, *, router: Any | None = None, max_iterations: int = 3,
                 use_worktree: bool = True, verification: VerificationConfig | None = None) -> None:
        self._primary_repo = Repo(repo_path)
        self._router = router or create_router()
        self._max_iterations = max_iterations
        self._use_worktree = use_worktree
        self._verification = verification or VerificationConfig()

    async def run(self, task: Task) -> TaskResult:
        max_iter = task.max_iterations or self._max_iterations
        task.repo_path = str(self._primary_repo.path)
        cfg = VerificationConfig(
            check_commands=self._verification.check_commands,
            check_policy_blocks=self._verification.check_policy_blocks,
            check_path_escapes=self._verification.check_path_escapes,
            check_python_syntax=self._verification.check_python_syntax,
            required_command_substrings=list(self._verification.required_command_substrings),
        )
        work_repo = self._primary_repo
        isolated = False
        if self._use_worktree:
            try:
                work_repo = self._primary_repo.create_worktree()
                isolated = True
            except Exception as e:
                logger.warning("Worktree creation failed (%s); using primary tree", e)

        worker = Worker(self._router, work_repo)
        arbiter = Arbiter(self._router, work_repo)
        worker_results: list[WorkerResult] = []
        arbiter_decisions: list[ArbiterDecision] = []
        try:
            try:
                await self._router.initialize()
            except Exception:
                pass
            for iteration in range(1, max_iter + 1):
                worker_result = await (worker.investigate(task) if iteration == 1 else worker.fix(
                    task, arbiter.format_feedback(arbiter_decisions[-1]), worker_results[-1]
                ))
                worker_results.append(worker_result)
                evidence = evaluate_hard_gates(worker_result, workspace=work_repo.path, config=cfg)
                decision = _decision_from_evidence(evidence) if not evidence.passed else await arbiter.review(task, worker_result)
                arbiter_decisions.append(decision)
                if decision.decision == Decision.ACCEPT or iteration == max_iter:
                    break

            final_diff = work_repo.git_diff()
            accepted = bool(arbiter_decisions and arbiter_decisions[-1].decision == Decision.ACCEPT)
            if isolated and accepted and final_diff.strip():
                apply_result = work_repo.apply_diff_to(self._primary_repo)
                if apply_result.returncode != 0:
                    failure = VerificationEvidence(
                        passed=False,
                        failures=[
                            # Keep this deterministic apply gate visible in the same evidence channel.
                            # The existing enum is intentionally reused for audit compatibility.
                        ],
                    )
                    arbiter_decisions[-1] = ArbiterDecision(
                        decision=Decision.REJECT,
                        confidence=1.0,
                        reason="Accepted diff could not be applied to primary tree: " + (apply_result.stderr or apply_result.stdout),
                        findings=[ArbiterFinding(severity="critical", description="Apply failure")],
                        required_changes=["Resolve the accepted diff application failure"],
                        model_used="apply-gate",
                    )
            return TaskResult(
                task=task,
                decision=arbiter_decisions[-1].decision if arbiter_decisions else Decision.REJECT,
                iterations=len(worker_results), worker_results=worker_results,
                arbiter_decisions=arbiter_decisions, final_diff=final_diff,
                commit_message=self._generate_commit_message(task, arbiter_decisions),
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
        return await Worker(self._router, self._primary_repo).investigate(task)

    async def review_only(self, task: Task, worker_result: WorkerResult) -> ArbiterDecision:
        try:
            await self._router.initialize()
        except Exception:
            pass
        evidence = evaluate_hard_gates(worker_result, workspace=self._primary_repo.path, config=self._verification)
        if not evidence.passed:
            return _decision_from_evidence(evidence)
        return await Arbiter(self._router, self._primary_repo).review(task, worker_result)

    def _generate_commit_message(self, task: Task, decisions: list[ArbiterDecision]) -> str:
        summary = task.description if len(task.description) <= 72 else task.description[:69] + "..."
        parts = [summary, ""]
        if decisions:
            last = decisions[-1]
            parts.append(f"Arbiter: {last.decision.value} (confidence: {last.confidence:.0%})")
            if last.reason:
                parts.append(f"Reason: {redact_secrets(last.reason)}")
        parts.extend(["", f"Iterations: {len(decisions)}"])
        return "\n".join(parts)
