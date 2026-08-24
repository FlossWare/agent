"""Regression tests for command-policy bypasses found during adversarial review."""

from __future__ import annotations

import subprocess

import pytest

from personal_agent.repo import Repo
from personal_agent.security import CommandPolicy, SecurityError


@pytest.fixture
def git_repo(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "main.py").write_text("print('ok')\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    return Repo(str(tmp_path))


class TestCommandPolicyBypassRegression:
    def test_find_exec_is_blocked(self):
        with pytest.raises(SecurityError):
            CommandPolicy().check(["find", ".", "-exec", "echo", "owned", ";"])

    def test_find_execdir_is_blocked(self):
        with pytest.raises(SecurityError):
            CommandPolicy().check(["find", ".", "-execdir", "echo", "owned", ";"])

    def test_git_submodule_update_requires_network(self):
        with pytest.raises(SecurityError):
            CommandPolicy(allow_network=False).check(
                ["git", "submodule", "update", "--init", "--recursive"]
            )

    def test_git_remote_update_requires_network(self):
        with pytest.raises(SecurityError):
            CommandPolicy(allow_network=False).check(
                ["git", "remote", "update"]
            )

    def test_git_concatenated_c_path_cannot_escape_workspace(self, tmp_path):
        policy = CommandPolicy(workspace=tmp_path)
        with pytest.raises(SecurityError):
            policy.check(["git", "-C/etc", "status"])

    def test_git_long_c_path_cannot_escape_workspace(self, tmp_path):
        policy = CommandPolicy(workspace=tmp_path)
        with pytest.raises(SecurityError):
            policy.check(["git", "-C", "/etc", "status"])

    def test_git_hook_write_is_blocked(self, git_repo):
        with pytest.raises(SecurityError):
            git_repo.write_file(".git/hooks/pre-commit", "#!/bin/sh\necho owned\n")

    def test_git_hook_nested_write_is_blocked(self, git_repo):
        with pytest.raises(SecurityError):
            git_repo.write_file(".git/hooks/nested/pre-push", "#!/bin/sh\necho owned\n")

    def test_git_submodule_update_is_allowed_when_network_explicitly_enabled(self):
        argv = CommandPolicy(allow_network=True).check(
            ["git", "submodule", "update", "--init"]
        )
        assert argv[:3] == ["git", "submodule", "update"]

    def test_remote_url_is_blocked_without_network(self):
        with pytest.raises(SecurityError):
            CommandPolicy().check(
                ["git", "remote", "add", "origin", "https://example.invalid/repo.git"]
            )
