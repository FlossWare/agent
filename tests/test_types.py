"""Tests for personal_agent.types."""

from personal_agent.types import (
    ArbiterDecision,
    ArbiterFinding,
    CommandResult,
    Decision,
    FileChange,
    Task,
    TaskResult,
    WorkerResult,
)


class TestTask:
    def test_defaults(self):
        t = Task(description="Fix bug", repo_path="/tmp")
        assert t.description == "Fix bug"
        assert t.repo_path == "/tmp"
        assert t.files == []
        assert t.commands == []
        assert t.max_iterations == 3

    def test_with_options(self):
        t = Task(
            description="Do work",
            repo_path="/repo",
            files=["a.py"],
            commands=["pytest"],
            max_iterations=5,
        )
        assert t.files == ["a.py"]
        assert t.commands == ["pytest"]
        assert t.max_iterations == 5


class TestCommandResult:
    def test_success(self):
        r = CommandResult(command="echo hi", returncode=0, stdout="hi\n")
        assert r.success

    def test_failure(self):
        r = CommandResult(command="false", returncode=1, stderr="fail")
        assert not r.success


class TestDecision:
    def test_values(self):
        assert Decision.ACCEPT.value == "accept"
        assert Decision.REJECT.value == "reject"

    def test_from_string(self):
        assert Decision("accept") == Decision.ACCEPT
        assert Decision("reject") == Decision.REJECT


class TestArbiterDecision:
    def test_defaults(self):
        d = ArbiterDecision()
        assert d.decision == Decision.REJECT
        assert d.confidence == 0.0
        assert d.findings == []
        assert d.required_changes == []

    def test_accepted(self):
        d = ArbiterDecision(
            decision=Decision.ACCEPT,
            confidence=0.95,
            reason="All tests pass",
        )
        assert d.decision == Decision.ACCEPT
        assert d.confidence == 0.95

    def test_with_findings(self):
        d = ArbiterDecision(
            decision=Decision.REJECT,
            findings=[
                ArbiterFinding(severity="high", description="Bug in line 42"),
            ],
            required_changes=["Fix the null check"],
        )
        assert len(d.findings) == 1
        assert d.findings[0].severity == "high"
        assert len(d.required_changes) == 1


class TestTaskResult:
    def test_defaults(self):
        r = TaskResult()
        assert r.decision == Decision.REJECT
        assert r.iterations == 0
        assert r.worker_results == []
        assert r.arbiter_decisions == []

    def test_exhausted(self):
        r = TaskResult()
        assert r.decision.value == "reject"
