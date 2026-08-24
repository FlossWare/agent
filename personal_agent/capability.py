"""Provider-neutral capability workers and arbitration.

A Worker is any capable unit of work. It does not have to be an LLM. It may
be deterministic code, a CLI, an MCP tool, another agent, a local model, or a
composite worker. The Arbiter dispatches work to capable workers and
synthesizes their evidence into a single result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence


@dataclass(frozen=True)
class Work:
    """A capability-oriented unit of work."""

    description: str
    required_capabilities: frozenset[str] = frozenset()
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkerResult:
    """Evidence returned by any worker."""

    worker: str
    success: bool
    evidence: Any
    confidence: float = 1.0
    capabilities: frozenset[str] = frozenset()
    metadata: dict[str, Any] = field(default_factory=dict)


class CapableWorker(Protocol):
    """Contract implemented by any executable unit of capability."""

    @property
    def name(self) -> str: ...

    @property
    def capabilities(self) -> frozenset[str]: ...

    async def execute(self, work: Work) -> WorkerResult: ...


@dataclass(frozen=True)
class Synthesis:
    """Arbiter's synthesized answer and supporting evidence."""

    conclusion: Any
    results: tuple[WorkerResult, ...]
    confidence: float
    disagreements: tuple[str, ...] = ()


class CapabilityArbiter:
    """Select capable workers, execute them, and synthesize their evidence.

    Selection is capability based. Provider, model, vendor, pricing, and
    execution mechanism are intentionally outside this abstraction.
    """

    def __init__(self, workers: Sequence[CapableWorker]) -> None:
        self._workers = tuple(workers)

    def select(self, work: Work) -> tuple[CapableWorker, ...]:
        required = work.required_capabilities
        return tuple(worker for worker in self._workers if required.issubset(worker.capabilities))

    async def execute(self, work: Work) -> Synthesis:
        selected = self.select(work)
        if not selected:
            raise LookupError(f"No worker satisfies capabilities: {sorted(work.required_capabilities)}")

        import asyncio
        results = tuple(await asyncio.gather(*(w.execute(work) for w in selected)))
        return self.synthesize(work, results)

    def synthesize(self, work: Work, results: Sequence[WorkerResult]) -> Synthesis:
        """Deterministically synthesize evidence without requiring an LLM."""
        successful = tuple(r for r in results if r.success)
        if not successful:
            return Synthesis(None, tuple(results), 0.0, ("All selected workers failed.",))

        evidence = tuple(r.evidence for r in successful)
        textual = tuple(str(item) for item in evidence)
        disagreements = (f"Workers returned different evidence: {textual}",) if len(set(textual)) > 1 else ()
        confidence = sum(max(0.0, min(1.0, r.confidence)) for r in successful) / len(successful)
        conclusion: Any = evidence[0] if len(evidence) == 1 else evidence
        return Synthesis(conclusion, tuple(results), confidence, disagreements)


class FunctionWorker:
    """Adapt an ordinary synchronous or asynchronous callable into a worker."""

    def __init__(self, name: str, capabilities: set[str], function: Any) -> None:
        self._name = name
        self._capabilities = frozenset(capabilities)
        self._function = function

    @property
    def name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> frozenset[str]:
        return self._capabilities

    async def execute(self, work: Work) -> WorkerResult:
        import inspect
        value = self._function(work)
        if inspect.isawaitable(value):
            value = await value
        return WorkerResult(self.name, True, value, capabilities=self.capabilities)
