"""Tests for deterministic verification gates (issue #5)."""

from pathlib import Path

from personal_agent.types import CommandResult, FileChange, WorkerResult
from personal_agent.verification import (
    GateKind,
    VerificationConfig,
    evaluate_hard_gates,
)


def _result(**kwargs) -> WorkerResult:
    return WorkerResult(**kwargs)


class TestHardGates:
    def test_passing_commands(self):
        wr = _result(test_results=[CommandResult(command="pytest", returncode=0)])
        ev = evaluate_hard_gates(wr)
        assert ev.passed

    def test_failed_command_blocks_accept(self):
        wr = _result(
            test_results=[CommandResult(command="pytest", returncode=1, stderr="fail")]
        )
        ev = evaluate_hard_gates(wr)
        assert not ev.passed
        assert any(f.kind == GateKind.COMMAND_FAILURE for f in ev.failures)

    def test_policy_block(self):
        wr = _result(
            test_results=[
                CommandResult(
                    command="sudo id",
                    returncode=-1,
                    stderr="Blocked by security policy: denied",
                )
            ]
        )
        ev = evaluate_hard_gates(wr)
        assert not ev.passed
        assert any(f.kind == GateKind.POLICY_VIOLATION for f in ev.failures)

    def test_python_syntax_error(self):
        wr = _result(
            changes=[
                FileChange(
                    path="bad.py",
                    action="modify",
                    content="def broken(\n    return 1\n",
                )
            ]
        )
        ev = evaluate_hard_gates(wr)
        assert not ev.passed
        assert any(f.kind == GateKind.SYNTAX_ERROR for f in ev.failures)

    def test_python_syntax_ok(self):
        wr = _result(
            changes=[
                FileChange(
                    path="ok.py",
                    action="modify",
                    content="def fine():\n    return 1\n",
                )
            ]
        )
        ev = evaluate_hard_gates(wr)
        assert ev.passed

    def test_path_escape(self, tmp_path):
        wr = _result(
            changes=[FileChange(path="../outside.py", action="create", content="x=1\n")]
        )
        ev = evaluate_hard_gates(wr, workspace=tmp_path)
        assert not ev.passed
        assert any(f.kind == GateKind.PATH_ESCAPE for f in ev.failures)

    def test_required_check_missing(self):
        wr = _result(test_results=[CommandResult(command="echo hi", returncode=0)])
        cfg = VerificationConfig(required_command_substrings=["pytest"])
        ev = evaluate_hard_gates(wr, config=cfg)
        assert not ev.passed
        assert any(f.kind == GateKind.REQUIRED_CHECK for f in ev.failures)

    def test_required_check_present(self):
        wr = _result(
            test_results=[CommandResult(command="pytest tests/", returncode=0)]
        )
        cfg = VerificationConfig(required_command_substrings=["pytest"])
        ev = evaluate_hard_gates(wr, config=cfg)
        assert ev.passed

    def test_llm_cannot_override_via_empty_failures_only(self):
        """Evidence with failures always reports passed=False."""
        wr = _result(
            test_results=[CommandResult(command="false", returncode=1)]
        )
        ev = evaluate_hard_gates(wr)
        assert ev.passed is False
        assert len(ev.reasons) >= 1
