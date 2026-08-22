"""Tests for personal_agent.arbiter."""

import json
import subprocess
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from personal_agent.arbiter import Arbiter
from personal_agent.repo import Repo
from personal_agent.types import (
    ArbiterDecision,
    ArbiterFinding,
    CommandResult,
    Decision,
    FileChange,
    Task,
    WorkerResult,
)


@dataclass
class FakeResponse:
    content: str = ""
    model: str = "arbiter-model"


@pytest.fixture
def git_repo(tmp_path):
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=str(tmp_path), capture_output=True)
    (tmp_path / "main.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True)
    return Repo(str(tmp_path))


@pytest.fixture
def mock_router():
    router = AsyncMock()
    router.chat = AsyncMock()
    return router


def make_decision_response(decision: str, confidence: float = 0.9, reason: str = "Looks good") -> FakeResponse:
    return FakeResponse(content=json.dumps({
        "decision": decision,
        "confidence": confidence,
        "reason": reason,
        "findings": [],
        "required_changes": [],
    }))


class TestArbiter:
    @pytest.mark.asyncio
    async def test_review_accept(self, git_repo, mock_router):
        mock_router.chat.return_value = make_decision_response("accept", 0.95, "All good")

        arbiter = Arbiter(mock_router, git_repo)
        task = Task(description="Add feature", repo_path=str(git_repo.path))
        worker_result = WorkerResult(plan="Added feature", changes=[])
        decision = await arbiter.review(task, worker_result)

        assert isinstance(decision, ArbiterDecision)
        assert decision.decision == Decision.ACCEPT
        assert decision.confidence == 0.95
        assert decision.model_used == "arbiter-model"

    @pytest.mark.asyncio
    async def test_review_reject_with_findings(self, git_repo, mock_router):
        mock_router.chat.return_value = FakeResponse(content=json.dumps({
            "decision": "reject",
            "confidence": 0.8,
            "reason": "Missing tests",
            "findings": [
                {
                    "severity": "high",
                    "description": "No test coverage",
                    "file": "main.py",
                    "suggestion": "Add unit tests",
                },
            ],
            "required_changes": ["Add tests for new function"],
        }))

        arbiter = Arbiter(mock_router, git_repo)
        task = Task(description="Fix bug", repo_path=str(git_repo.path))
        worker_result = WorkerResult(plan="Fixed it", changes=[
            FileChange(path="main.py", action="modify", content="x = 2\n"),
        ])
        decision = await arbiter.review(task, worker_result)

        assert decision.decision == Decision.REJECT
        assert len(decision.findings) == 1
        assert decision.findings[0].severity == "high"
        assert decision.required_changes == ["Add tests for new function"]

    @pytest.mark.asyncio
    async def test_review_handles_invalid_json(self, git_repo, mock_router):
        mock_router.chat.return_value = FakeResponse(content="This is not JSON at all")

        arbiter = Arbiter(mock_router, git_repo)
        task = Task(description="Check", repo_path=str(git_repo.path))
        decision = await arbiter.review(task, WorkerResult())

        assert decision.decision == Decision.REJECT
        assert decision.confidence == 0.0

    @pytest.mark.asyncio
    async def test_review_handles_markdown_wrapped_json(self, git_repo, mock_router):
        mock_router.chat.return_value = FakeResponse(
            content='Here is my review:\n```json\n{"decision": "accept", "confidence": 0.85, "reason": "Fine"}\n```\n'
        )

        arbiter = Arbiter(mock_router, git_repo)
        task = Task(description="Review", repo_path=str(git_repo.path))
        decision = await arbiter.review(task, WorkerResult())

        assert decision.decision == Decision.ACCEPT
        assert decision.confidence == 0.85

    @pytest.mark.asyncio
    async def test_review_includes_test_results(self, git_repo, mock_router):
        mock_router.chat.return_value = make_decision_response("accept")

        arbiter = Arbiter(mock_router, git_repo)
        task = Task(description="Fix", repo_path=str(git_repo.path))
        worker_result = WorkerResult(
            plan="Fixed",
            test_results=[
                CommandResult(command="pytest", returncode=0, stdout="1 passed"),
            ],
        )
        decision = await arbiter.review(task, worker_result)

        assert decision.decision == Decision.ACCEPT


class TestFormatFeedback:
    def test_accept_feedback(self):
        arbiter = Arbiter.__new__(Arbiter)
        decision = ArbiterDecision(
            decision=Decision.ACCEPT,
            confidence=0.95,
            reason="Everything looks correct",
        )
        feedback = arbiter.format_feedback(decision)
        assert "ACCEPT" in feedback
        assert "Everything looks correct" in feedback

    def test_reject_with_findings_and_changes(self):
        arbiter = Arbiter.__new__(Arbiter)
        decision = ArbiterDecision(
            decision=Decision.REJECT,
            confidence=0.7,
            reason="Issues found",
            findings=[
                ArbiterFinding(severity="high", description="Null check missing", file="auth.py", suggestion="Add null check"),
                ArbiterFinding(severity="low", description="Style issue"),
            ],
            required_changes=["Add null check in auth.py line 42"],
        )
        feedback = arbiter.format_feedback(decision)
        assert "REJECT" in feedback
        assert "Null check missing" in feedback
        assert "auth.py" in feedback
        assert "Add null check" in feedback
        assert "Style issue" in feedback
        assert "REQUIRED CHANGES" in feedback
