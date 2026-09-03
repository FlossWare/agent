"""Tests for the canonical provider-neutral worker contract."""

from __future__ import annotations

import asyncio

from personal_agent.capability import CapabilityArbiter, FunctionWorker
from personal_agent.coding_worker import CodingWorkerAdapter
from personal_agent.types import CapableWorker, Task, Work, WorkerResult


def test_work_and_worker_result_are_canonical_types():
    work = Work(description="inspect")
    result = WorkerResult(worker="test", evidence="ok")

    assert work.required_capabilities == frozenset()
    assert result.worker == "test"
    assert result.evidence == "ok"
    assert isinstance(result.capabilities, frozenset)


def test_task_is_a_work_specialization():
    task = Task(description="fix", repo_path="/repo")

    assert isinstance(task, Work)
    assert task.description == "fix"
    assert task.repo_path == "/repo"


def test_function_worker_returns_canonical_result():
    worker = FunctionWorker("checker", {"test"}, lambda work: work.description)

    result = asyncio.run(
        worker.execute(Work(description="check", required_capabilities=frozenset({"test"})))
    )

    assert isinstance(result, WorkerResult)
    assert result.worker == "checker"
    assert result.success
    assert result.evidence == "check"
    assert result.capabilities == frozenset({"test"})


def test_capability_arbiter_consumes_canonical_result():
    worker = FunctionWorker("checker", {"test"}, lambda work: "accepted")
    arbiter = CapabilityArbiter([worker])

    synthesis = asyncio.run(
        arbiter.execute(Work(description="check", required_capabilities=frozenset({"test"})))
    )

    assert synthesis.conclusion == "accepted"
    assert len(synthesis.results) == 1
    assert isinstance(synthesis.results[0], WorkerResult)


def test_canonical_worker_protocol_is_runtime_shape():
    worker = FunctionWorker("checker", {"test"}, lambda work: "ok")

    assert isinstance(worker, CapableWorker)


def test_coding_worker_adapter_merges_metadata():
    """Pre-existing routing provenance on WorkerResult must survive adaptation."""

    class _StubWorker:
        async def investigate(self, task):
            return WorkerResult(
                plan="p",
                model_used="unit-model",
                metadata={"route": "preferred", "account": "free"},
            )

    adapter = CodingWorkerAdapter(_StubWorker(), name="coding-worker")
    result = asyncio.run(adapter.execute(Work(description="inspect")))

    assert result.metadata["route"] == "preferred"
    assert result.metadata["account"] == "free"
    assert result.metadata["model"] == "unit-model"
    assert result.metadata["execution"] == "coding-worker"
    assert result.worker == "coding-worker"
