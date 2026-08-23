"""Deterministic verification gates that override LLM acceptance.

Hard gates always win over arbiter ACCEPT decisions. They produce
structured VerificationEvidence for audit trails.
"""

from __future__ import annotations

import py_compile
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable

from personal_agent.security import SecurityError, resolve_in_workspace
from personal_agent.types import CommandResult, FileChange, WorkerResult


class GateKind(str, Enum):
    COMMAND_FAILURE = "command_failure"
    POLICY_VIOLATION = "policy_violation"
    PATH_ESCAPE = "path_escape"
    SYNTAX_ERROR = "syntax_error"
    REQUIRED_CHECK = "required_check"
    APPLY_FAILURE = "apply_failure"


@dataclass
class GateFailure:
    kind: GateKind
    message: str
    detail: str = ""


@dataclass
class VerificationEvidence:
    """Structured result of deterministic verification."""

    passed: bool = True
    failures: list[GateFailure] = field(default_factory=list)

    @property
    def reasons(self) -> list[str]:
        return [f"[{f.kind.value}] {f.message}" for f in self.failures]


@dataclass
class VerificationConfig:
    """Which hard gates to run."""

    check_commands: bool = True
    check_policy_blocks: bool = True
    check_path_escapes: bool = True
    check_python_syntax: bool = True
    # Command substrings that must appear among successful test_results
    # when non-empty (e.g. ["pytest"]).
    required_command_substrings: list[str] = field(default_factory=list)


DEFAULT_VERIFICATION = VerificationConfig()


def evaluate_hard_gates(
    worker_result: WorkerResult,
    *,
    workspace: Path | None = None,
    config: VerificationConfig | None = None,
) -> VerificationEvidence:
    """Run deterministic gates. Any failure means ACCEPT is forbidden."""
    cfg = config or DEFAULT_VERIFICATION
    failures: list[GateFailure] = []

    if cfg.check_commands or cfg.check_policy_blocks:
        for tr in worker_result.test_results:
            if tr.returncode == 0:
                continue
            stderr = tr.stderr or ""
            if cfg.check_policy_blocks and "Blocked by security policy" in stderr:
                failures.append(GateFailure(
                    kind=GateKind.POLICY_VIOLATION,
                    message=f"Security policy violation: {tr.command}",
                    detail=stderr[:500],
                ))
            elif cfg.check_commands:
                failures.append(GateFailure(
                    kind=GateKind.COMMAND_FAILURE,
                    message=f"Command failed (exit {tr.returncode}): {tr.command}",
                    detail=(stderr or tr.stdout or "")[:500],
                ))

    if cfg.check_path_escapes and workspace is not None:
        for change in worker_result.changes:
            try:
                resolve_in_workspace(workspace, change.path)
            except SecurityError as e:
                failures.append(GateFailure(
                    kind=GateKind.PATH_ESCAPE,
                    message=f"Path escape in change: {change.path}",
                    detail=str(e),
                ))

    if cfg.check_python_syntax:
        for change in worker_result.changes:
            if change.action == "delete":
                continue
            if not change.path.endswith(".py"):
                continue
            if not change.content:
                continue
            err = _python_syntax_error(change.content)
            if err:
                failures.append(GateFailure(
                    kind=GateKind.SYNTAX_ERROR,
                    message=f"Python syntax error in {change.path}",
                    detail=err,
                ))

    if cfg.required_command_substrings:
        successful = " ".join(
            tr.command for tr in worker_result.test_results if tr.returncode == 0
        )
        for req in cfg.required_command_substrings:
            if req not in successful:
                failures.append(GateFailure(
                    kind=GateKind.REQUIRED_CHECK,
                    message=f"Required check not run successfully: {req!r}",
                    detail=f"Successful commands: {successful or '(none)'}",
                ))

    return VerificationEvidence(passed=not failures, failures=failures)


def _python_syntax_error(source: str) -> str | None:
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
            fh.write(source)
            path = fh.name
        try:
            py_compile.compile(path, doraise=True)
        finally:
            Path(path).unlink(missing_ok=True)
        return None
    except py_compile.PyCompileError as e:
        return str(e)
    except Exception as e:
        return str(e)
