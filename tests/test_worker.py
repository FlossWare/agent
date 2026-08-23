"""Tests for personal_agent.worker."""

import json
import subprocess
from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from personal_agent.repo import Repo
from personal_agent.types import Task, WorkerResult
from personal_agent.worker import Worker


@dataclass
class FakeResponse:
    content: str = ""
    model: str = "test-model"
    provider: str = "test"


@pytest.fixture
def git_repo(tmp_path):
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t.com"],
        cwd=str(tmp_path),
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "T"], cwd=str(tmp_path), capture_output=True
    )
    (tmp_path / "main.py").write_text("def greet():\n    return 'hello'\n")
    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True
    )
    return Repo(str(tmp_path))


@pytest.fixture
def mock_router():
    router = AsyncMock()
    router.chat = AsyncMock()
    return router


def make_response(data: dict) -> FakeResponse:
    return FakeResponse(content=json.dumps(data))


class TestWorker:
    @pytest.mark.asyncio
    async def test_investigate_returns_worker_result(self, git_repo, mock_router):
        mock_router.chat.return_value = make_response(
            {
                "plan": "Read the code",
                "findings": ["main.py has a greet function"],
                "changes": [],
                "commands_to_run": [],
            }
        )

        worker = Worker(mock_router, git_repo)
        task = Task(description="Investigate the repo", repo_path=str(git_repo.path))
        result = await worker.investigate(task)

        assert isinstance(result, WorkerResult)
        assert result.plan == "Read the code"
        assert len(result.findings) == 1
        assert result.model_used == "test-model"

    @pytest.mark.asyncio
    async def test_investigate_applies_changes(self, git_repo, mock_router):
        mock_router.chat.return_value = make_response(
            {
                "plan": "Add a new file",
                "findings": [],
                "changes": [
                    {"path": "helper.py", "action": "create", "content": "x = 1\n"},
                ],
                "commands_to_run": [],
            }
        )

        worker = Worker(mock_router, git_repo)
        task = Task(description="Add helper", repo_path=str(git_repo.path))
        result = await worker.investigate(task)

        assert len(result.changes) == 1
        assert git_repo.read_file("helper.py") == "x = 1\n"

    @pytest.mark.asyncio
    async def test_investigate_runs_safe_commands(self, git_repo, mock_router):
        mock_router.chat.return_value = make_response(
            {
                "plan": "Check something",
                "findings": [],
                "changes": [],
                "commands_to_run": ["echo test"],
            }
        )

        worker = Worker(mock_router, git_repo)
        task = Task(description="Check", repo_path=str(git_repo.path))
        result = await worker.investigate(task)

        assert len(result.test_results) >= 1
        assert result.test_results[0].success

    @pytest.mark.asyncio
    async def test_investigate_blocks_dangerous_commands(self, git_repo, mock_router):
        mock_router.chat.return_value = make_response(
            {
                "plan": "Destroy everything",
                "findings": [],
                "changes": [],
                "commands_to_run": ["rm -rf /"],
            }
        )

        worker = Worker(mock_router, git_repo)
        task = Task(description="Bad", repo_path=str(git_repo.path))
        result = await worker.investigate(task)

        assert result.test_results[0].returncode == -1
        assert "Blocked by security policy" in result.test_results[0].stderr

    @pytest.mark.asyncio
    async def test_investigate_blocks_sudo(self, git_repo, mock_router):
        mock_router.chat.return_value = make_response(
            {
                "plan": "Escalate",
                "findings": [],
                "changes": [],
                "commands_to_run": ["sudo id"],
            }
        )

        worker = Worker(mock_router, git_repo)
        task = Task(description="Bad", repo_path=str(git_repo.path))
        result = await worker.investigate(task)

        assert result.test_results[0].returncode == -1
        assert "security policy" in result.test_results[0].stderr.lower()

    @pytest.mark.asyncio
    async def test_investigate_runs_task_commands(self, git_repo, mock_router):
        mock_router.chat.return_value = make_response(
            {
                "plan": "No changes",
                "findings": [],
                "changes": [],
                "commands_to_run": [],
            }
        )

        worker = Worker(mock_router, git_repo)
        task = Task(
            description="Run tests",
            repo_path=str(git_repo.path),
            commands=["echo passed"],
        )
        result = await worker.investigate(task)

        assert any("passed" in r.stdout for r in result.test_results)

    @pytest.mark.asyncio
    async def test_fix_includes_feedback(self, git_repo, mock_router):
        mock_router.chat.return_value = make_response(
            {
                "plan": "Fix the issue",
                "findings": ["Fixed the return value"],
                "changes": [
                    {
                        "path": "main.py",
                        "action": "modify",
                        "content": "def greet():\n    return 'fixed'\n",
                    },
                ],
                "commands_to_run": [],
            }
        )

        previous = WorkerResult(plan="first try", test_results=[])

        worker = Worker(mock_router, git_repo)
        task = Task(description="Fix greet", repo_path=str(git_repo.path))
        result = await worker.fix(task, "Return value is wrong", previous)

        assert result.plan == "Fix the issue"
        assert git_repo.read_file("main.py") == "def greet():\n    return 'fixed'\n"

    @pytest.mark.asyncio
    async def test_parse_response_handles_markdown_json(self, git_repo, mock_router):
        mock_router.chat.return_value = FakeResponse(
            content=(
                'Some text\n```json\n{"plan": "test", "findings": [], '
                '"changes": [], "commands_to_run": []}\n```\nMore text'
            )
        )

        worker = Worker(mock_router, git_repo)
        task = Task(description="Test parsing", repo_path=str(git_repo.path))
        result = await worker.investigate(task)

        assert result.plan == "test"

    @pytest.mark.asyncio
    async def test_parse_response_handles_invalid_json(self, git_repo, mock_router):
        mock_router.chat.return_value = FakeResponse(
            content="Just plain text with no JSON"
        )

        worker = Worker(mock_router, git_repo)
        task = Task(description="Test fallback", repo_path=str(git_repo.path))
        result = await worker.investigate(task)

        assert result.plan != ""
        assert result.changes == []

    @pytest.mark.asyncio
    async def test_parse_response_handles_triple_quoted_json(
        self, git_repo, mock_router
    ):
        raw = (
            '```json\n{"plan": "fix", "findings": [], "changes": '
            '[{"path": "x.py", "action": "modify", "content": """def hello():\n'
            '    return 1\n"""}], "commands_to_run": []}\n```'
        )
        mock_router.chat.return_value = FakeResponse(content=raw)

        worker = Worker(mock_router, git_repo)
        task = Task(description="Test triple-quote fix", repo_path=str(git_repo.path))
        result = await worker.investigate(task)

        assert result.plan == "fix"
        assert len(result.changes) == 1
        assert "def hello" in result.changes[0].content

    def test_fix_malformed_json_triple_quotes(self):
        text = '{"key": """hello\nworld""", "other": 1}'
        result = Worker._fix_malformed_json(text)
        assert result is not None
        assert "hello\nworld" in result["key"]
        assert result["other"] == 1

    def test_fix_malformed_json_escaped_inner_quotes(self):
        text = r'{"content": """\"\"\"docstring\"\"\"\nx = 1"""}'
        result = Worker._fix_malformed_json(text)
        assert result is not None
        assert '"""docstring"""' in result["content"]
        assert "x = 1" in result["content"]

    def test_fix_malformed_json_trailing_comma(self):
        text = '{"a": 1, "b": 2, }'
        result = Worker._fix_malformed_json(text)
        assert result is not None
        assert result["a"] == 1
