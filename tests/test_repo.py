"""Tests for personal_agent.repo."""

import os
import subprocess
import tempfile

import pytest

from personal_agent.repo import Repo
from personal_agent.types import FileChange


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repo with some files."""
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), capture_output=True)

    (tmp_path / "main.py").write_text("def hello():\n    return 'world'\n")
    (tmp_path / "test_main.py").write_text("from main import hello\ndef test_hello():\n    assert hello() == 'world'\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "util.py").write_text("def add(a, b):\n    return a + b\n")

    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=str(tmp_path), capture_output=True)

    return Repo(str(tmp_path))


class TestRepo:
    def test_not_a_repo(self, tmp_path):
        with pytest.raises(ValueError, match="Not a git repository"):
            Repo(str(tmp_path))

    def test_read_file(self, git_repo):
        content = git_repo.read_file("main.py")
        assert "def hello" in content

    def test_read_missing_file(self, git_repo):
        with pytest.raises(FileNotFoundError):
            git_repo.read_file("nonexistent.py")

    def test_write_file(self, git_repo):
        git_repo.write_file("new.py", "x = 1\n")
        assert git_repo.read_file("new.py") == "x = 1\n"

    def test_write_nested(self, git_repo):
        git_repo.write_file("deep/nested/file.py", "y = 2\n")
        assert git_repo.read_file("deep/nested/file.py") == "y = 2\n"

    def test_list_files(self, git_repo):
        files = git_repo.list_files()
        assert "main.py" in files
        assert "sub/util.py" in files

    def test_grep(self, git_repo):
        results = git_repo.grep("def hello")
        assert len(results) >= 1
        assert results[0][0] == "main.py"

    def test_git_status(self, git_repo):
        status = git_repo.git_status()
        assert status == ""  # clean after initial commit

        git_repo.write_file("new.py", "x = 1\n")
        status = git_repo.git_status()
        assert "new.py" in status

    def test_git_diff(self, git_repo):
        git_repo.write_file("main.py", "def hello():\n    return 'changed'\n")
        diff = git_repo.git_diff()
        assert "changed" in diff

    def test_git_log(self, git_repo):
        log = git_repo.git_log()
        assert "initial" in log

    def test_run_command(self, git_repo):
        result = git_repo.run_command("echo hello")
        assert result.success
        assert "hello" in result.stdout

    def test_run_command_failure(self, git_repo):
        result = git_repo.run_command("false")
        assert not result.success

    def test_apply_changes(self, git_repo):
        changes = [
            FileChange(path="main.py", action="modify", content="def hello():\n    return 'updated'\n"),
            FileChange(path="new_file.py", action="create", content="x = 42\n"),
        ]
        results = git_repo.apply_changes(changes)
        assert len(results) == 2
        assert git_repo.read_file("main.py") == "def hello():\n    return 'updated'\n"
        assert git_repo.read_file("new_file.py") == "x = 42\n"

    def test_apply_delete(self, git_repo):
        changes = [FileChange(path="main.py", action="delete")]
        git_repo.apply_changes(changes)
        with pytest.raises(FileNotFoundError):
            git_repo.read_file("main.py")

    def test_tree(self, git_repo):
        tree = git_repo.tree()
        assert "main.py" in tree
        assert "sub" in tree
