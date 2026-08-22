"""Tests for personal_agent.agent (CodingAgent orchestration)."""

import json
import subprocess
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from personal_agent.agent import CodingAgent
from personal_agent.types import Decision, Task


@dataclass
class FakeResponse:
    content: str = ""
    model: str = "test-model"


def worker_response(plan="Did the work", changes=None, commands=None):
    return FakeResponse(content=json.dumps({
        "plan": plan,
        "findings": ["Investigated"],
        "changes": changes or [],
        "commands_to_run": commands or [],
    }))


def arbiter_accept(reason="Looks good", confidence=0.95):
    return FakeResponse(content=json.dumps({
        "decision": "accept",
        "confidence": confidence,
        "reason": reason,
        "findings": [],
        "required_changes": [],
    }))


def arbiter_reject(reason="Needs work", required=None):
    return FakeResponse(content=json.dumps({
        "decision": "reject",
        "confidence": 0.6,
        "reason": reason,
        "findings": [{"severity": "high", "description": reason}],
        "required_changes": required or ["Fix the issue"],
    }))


@pytest.fixture
def git_repo(tmp_path):
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=str(tmp_path), capture_output=True)
    (tmp_path / "main.py").write_text("def main():\n    pass\n")
    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True)
    return tmp_path


class TestCodingAgent:
    @pytest.mark.asyncio
    async def test_accept_on_first_iteration(self, git_repo):
        mock_router = AsyncMock()
        mock_router.initialize = AsyncMock()
        mock_router.chat = AsyncMock(side_effect=[
            worker_response(),
            arbiter_accept(),
        ])

        agent = CodingAgent(str(git_repo), router=mock_router)
        task = Task(description="Add logging", repo_path=str(git_repo))
        result = await agent.run(task)

        assert result.decision == Decision.ACCEPT
        assert result.iterations == 1
        assert len(result.worker_results) == 1
        assert len(result.arbiter_decisions) == 1
        assert "Add logging" in result.commit_message

    @pytest.mark.asyncio
    async def test_reject_then_accept(self, git_repo):
        mock_router = AsyncMock()
        mock_router.initialize = AsyncMock()
        mock_router.chat = AsyncMock(side_effect=[
            worker_response("First attempt"),
            arbiter_reject("Missing tests"),
            worker_response("Second attempt with tests"),
            arbiter_accept("Tests added"),
        ])

        agent = CodingAgent(str(git_repo), router=mock_router)
        task = Task(description="Fix bug", repo_path=str(git_repo), max_iterations=3)
        result = await agent.run(task)

        assert result.decision == Decision.ACCEPT
        assert result.iterations == 2

    @pytest.mark.asyncio
    async def test_max_iterations_exhausted(self, git_repo):
        mock_router = AsyncMock()
        mock_router.initialize = AsyncMock()
        mock_router.chat = AsyncMock(side_effect=[
            worker_response("Try 1"),
            arbiter_reject("Still wrong"),
            worker_response("Try 2"),
            arbiter_reject("Still wrong"),
        ])

        agent = CodingAgent(str(git_repo), router=mock_router)
        task = Task(description="Impossible task", repo_path=str(git_repo), max_iterations=2)
        result = await agent.run(task)

        assert result.decision == Decision.REJECT
        assert result.iterations == 2

    @pytest.mark.asyncio
    async def test_investigate_only(self, git_repo):
        mock_router = AsyncMock()
        mock_router.initialize = AsyncMock()
        mock_router.chat = AsyncMock(return_value=worker_response("Just investigating"))

        agent = CodingAgent(str(git_repo), router=mock_router)
        task = Task(description="What does this do?", repo_path=str(git_repo))
        result = await agent.investigate_only(task)

        assert result.plan == "Just investigating"

    @pytest.mark.asyncio
    async def test_commit_message_truncates_long_descriptions(self, git_repo):
        mock_router = AsyncMock()
        mock_router.initialize = AsyncMock()
        mock_router.chat = AsyncMock(side_effect=[
            worker_response(),
            arbiter_accept(),
        ])

        agent = CodingAgent(str(git_repo), router=mock_router)
        task = Task(description="A" * 100, repo_path=str(git_repo))
        result = await agent.run(task)

        first_line = result.commit_message.split("\n")[0]
        assert len(first_line) <= 72

    @pytest.mark.asyncio
    async def test_not_a_git_repo(self, tmp_path):
        with pytest.raises(ValueError, match="Not a git repository"):
            CodingAgent(str(tmp_path))
