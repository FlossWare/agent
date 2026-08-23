"""Regression tests for escapes called out in the Claude PR review."""

from __future__ import annotations

import subprocess

import pytest

from personal_agent.repo import Repo
from personal_agent.security import (
    CommandPolicy,
    SecurityError,
    sanitize_worker_environ,
)


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
    (tmp_path / "main.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True
    )
    return Repo(str(tmp_path))


class TestFindExecBypass:
    def test_find_exec_denied(self):
        with pytest.raises(SecurityError, match="find action"):
            CommandPolicy().check(["find", ".", "-exec", "cat", "{}", ";"])

    def test_find_execdir_denied(self):
        with pytest.raises(SecurityError):
            CommandPolicy().check("find /tmp -execdir rm {} +")

    def test_find_delete_denied(self):
        with pytest.raises(SecurityError):
            CommandPolicy().check(["find", ".", "-delete"])

    def test_find_name_allowed(self):
        argv = CommandPolicy().check(["find", ".", "-name", "*.py"])
        assert argv[0] == "find"


class TestGitNetwork:
    def test_git_clone_denied(self):
        with pytest.raises(SecurityError, match="network"):
            CommandPolicy().check("git clone https://evil.example/r.git")

    def test_git_fetch_denied(self):
        with pytest.raises(SecurityError):
            CommandPolicy().check(["git", "fetch", "origin"])

    def test_git_push_denied(self):
        with pytest.raises(SecurityError):
            CommandPolicy().check("git push origin main")

    def test_git_status_allowed(self):
        argv = CommandPolicy().check(["git", "status", "--short"])
        assert argv[1] == "status"

    def test_git_url_on_local_subcommand_denied(self):
        with pytest.raises(SecurityError, match="URL"):
            CommandPolicy().check(
                ["git", "remote", "add", "evil", "https://evil.example/r.git"]
            )

    def test_git_clone_allowed_with_network(self):
        # Subcommand allowed when capability enabled (URL still may be used)
        argv = CommandPolicy(allow_network=True).check(
            ["git", "clone", "https://example.com/r.git"]
        )
        assert argv[1] == "clone"


class TestGitHooksWrite:
    def test_write_git_hooks_blocked(self, git_repo):
        with pytest.raises(SecurityError, match="\.git"):
            git_repo.write_file(
                ".git/hooks/pre-commit", "#!/bin/sh\ncurl http://evil\n"
            )

    def test_write_git_config_blocked(self, git_repo):
        with pytest.raises(SecurityError, match="\.git"):
            git_repo.write_file(".git/config", "[core]\n\tbare = true\n")

    def test_apply_change_git_hooks_blocked(self, git_repo):
        from personal_agent.types import FileChange

        results = git_repo.apply_changes(
            [
                FileChange(
                    path=".git/hooks/post-commit",
                    action="create",
                    content="#!/bin/sh\necho pwned\n",
                )
            ]
        )
        assert results[0].returncode == -1
        assert "security policy" in results[0].stderr.lower()


class TestShortOptPathArgs:
    def test_tar_c_embedded_path(self):
        with pytest.raises(SecurityError):
            CommandPolicy(workspace=__import__("pathlib").Path("/tmp")).check(
                ["tar", "-C/etc", "-xf", "x.tar"]
            )

    def test_cp_t_outside(self, git_repo):
        with pytest.raises(SecurityError):
            CommandPolicy(workspace=git_repo.path).check(
                ["cp", "-t/etc", "main.py"]
            )


class TestEnvAllowlist:
    def test_stripe_key_dropped(self):
        clean = sanitize_worker_environ(
            {"STRIPE_KEY": "sk_live_xxx", "PATH": "/usr/bin"}
        )
        assert "STRIPE_KEY" not in clean
        assert clean["PATH"] == "/usr/bin"

    def test_slack_webhook_dropped(self):
        clean = sanitize_worker_environ(
            {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/x", "HOME": "/home/u"}
        )
        assert "SLACK_WEBHOOK_URL" not in clean

    def test_db_conn_dropped(self):
        clean = sanitize_worker_environ(
            {"DB_CONN_STRING": "postgres://x", "LANG": "C"}
        )
        assert "DB_CONN_STRING" not in clean
        assert clean["LANG"] == "C"
