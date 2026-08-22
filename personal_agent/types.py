"""Data types for personal-agent workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Decision(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"


@dataclass
class Task:
    """A coding task to be executed by workers."""

    description: str
    repo_path: str
    files: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
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
    """Output from a worker's investigation/implementation phase."""

    plan: str = ""
    findings: list[str] = field(default_factory=list)
    changes: list[FileChange] = field(default_factory=list)
    test_results: list[CommandResult] = field(default_factory=list)
    model_used: str = ""
    raw_response: str = ""


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
