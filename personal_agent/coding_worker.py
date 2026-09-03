"""Adapter that exposes the existing coding Worker through the canonical protocol."""

from __future__ import annotations

from personal_agent.types import Task, Work, WorkerResult
from personal_agent.worker import Worker


class CodingWorkerAdapter:
    """Adapt the coding-oriented Worker to the provider-neutral worker contract.

    The adapter preserves the existing investigation/fix implementation while
    making its boundary compatible with ``CapableWorker``. Provider and model
    selection remain concerns of the injected router.
    """

    def __init__(self, worker: Worker, *, name: str = "coding-worker") -> None:
        self._worker = worker
        self._name = name
        self._capabilities = frozenset({"code", "repository"})

    @property
    def name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> frozenset[str]:
        return self._capabilities

    async def execute(self, work: Work) -> WorkerResult:
        """Execute coding work and return the canonical result envelope."""
        if isinstance(work, Task):
            task = work
        else:
            task = Task(
                description=work.description,
                required_capabilities=work.required_capabilities,
                context=work.context,
            )
        result = await self._worker.investigate(task)
        result.worker = self.name
        result.success = all(test.success for test in result.test_results) if result.test_results else True
        result.capabilities = self.capabilities
        result.evidence = {
            "plan": result.plan,
            "findings": result.findings,
            "changes": result.changes,
            "test_results": result.test_results,
        }
        # Merge so routing/provenance already set by the underlying worker is kept.
        result.metadata = {
            **(result.metadata or {}),
            "model": result.model_used,
            "execution": "coding-worker",
        }
        return result
