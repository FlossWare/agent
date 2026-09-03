"""Canonical provider-neutral work and result contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class Decision(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"


@dataclass(frozen=True)
class Work:
    """Provider-neutral unit of work submitted to a capable worker."""

    description: str
    required_capabilities: frozenset[str] = frozenset()
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class Task(Work):
    """Coding-task specialization carrying repository execution details."""

    repo_path: str = ""
    files: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    max_iterations: int = 3


@dataclass
class FileChange:
    """A single file modification made by a worker."""

    path: str
    action: str = "modify"
    content: str = ""
    diff: str = ""


@dataclass
class CommandResult:
    """Result of running a shell command."""

    command: str
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""

    @property
    def success(self) -> bool:
        return self.returncode == 0


@dataclass
class WorkerResult:
    """Canonical evidence envelope returned by every worker.

    The generic fields form the stable worker protocol. Coding-oriented fields
    remain available for compatibility and are treated as structured evidence,
    not as requirements imposed on non-coding workers.
    """

    worker: str = ""
    success: bool = True
    evidence: Any = None
    confidence: float = 1.0
    capabilities: frozenset[str] = frozenset()
    metadata: dict[str, Any] = field(default_factory=dict)
    plan: str = ""
    findings: list[str] = field(default_factory=list)
    changes: list[FileChange] = field(default_factory=list)
    test_results: list[CommandResult] = field(default_factory=list)
    model_used: str = ""
    raw_response: str = ""


@runtime_checkable
class CapableWorker(Protocol):
    """Canonical executable worker contract."""

    @property
    def name(self) -> str: ...

    @property
    def capabilities(self) -> frozenset[str]: ...

    async def execute(self, work: Work) -> WorkerResult: ...


@dataclass
class ArbiterFinding:
    """A single finding from the arbiter's review."""

    severity: str = "medium"
    description: str = ""
    file: str = ""
    suggestion: str = ""


@dataclass
class ArbiterDecision:
    """Structured decision from the arbiter."""

    decision: Decision = Decision.REJECT
    confidence: float = 0.0
    reason: str = ""
    findings: list[ArbiterFinding] = field(default_factory=list)
    required_changes: list[str] = field(default_factory=list)
    model_used: str = ""


@dataclass
class TaskResult:
    """Final result of a complete task execution."""

    task: Task | None = None
    decision: Decision = Decision.REJECT
    iterations: int = 0
    worker_results: list[WorkerResult] = field(default_factory=list)
    arbiter_decisions: list[ArbiterDecision] = field(default_factory=list)
    final_diff: str = ""
    commit_message: str = ""
