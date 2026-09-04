from __future__ import annotations

import json
import os
import subprocess

import pytest

from personal_agent.github import GitHubClient, GitHubError


def test_create_pull_request_parses_machine_output(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        assert kwargs["env"]["GH_TOKEN"] == "test-token"
        assert kwargs["env"]["GITHUB_TOKEN"] == "test-token-2"
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"number": 42, "url": "https://github.com/FlossWare/agent/pull/42", "title": "Fix"}),
            stderr="",
        )

    monkeypatch.setenv("GH_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token-2")
    monkeypatch.setattr(subprocess, "run", fake_run)
    pr = GitHubClient("FlossWare/agent").create_pull_request(
        title="Fix",
        body="Fixes #42",
        head="fix/42",
    )

    assert pr.number == 42
    assert pr.title == "Fix"
    assert calls[0][0] == "gh"
    assert "--repo" in calls[0]


def test_github_client_does_not_persist_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_TOKEN", "secret")
    client = GitHubClient("FlossWare/agent")
    assert client.repository == "FlossWare/agent"
    assert client.timeout == 30
    assert not hasattr(client, "token")
    assert not hasattr(client, "credential")


def test_missing_gh_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(GitHubError, match="GitHub CLI"):
        GitHubClient().status()


def test_gh_failure_is_not_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="permission denied")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(GitHubError, match="permission denied"):
        GitHubClient("FlossWare/agent").view_pull_request(1)
