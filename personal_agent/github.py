"""GitHub CLI integration for guarded repository publication.

The adapter deliberately uses the authenticated ``gh`` CLI instead of storing
GitHub credentials in the agent process. It is an integration boundary, not a
second Git implementation. All mutating operations are explicit methods so
callers can map them to the autonomous-engineering authority levels.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Sequence


class GitHubError(RuntimeError):
    """Raised when a GitHub CLI operation cannot be completed."""


@dataclass(frozen=True)
class PullRequest:
    """Minimal pull-request identity returned by the adapter."""

    number: int
    url: str
    title: str


class GitHubClient:
    """Small, credential-free GitHub adapter backed by ``gh``."""

    def __init__(self, repository: str | None = None, *, timeout: int = 30) -> None:
        self.repository = repository
        self.timeout = timeout

    def _run(self, args: Sequence[str], *, check: bool = True) -> str:
        command = ["gh", *args]
        if self.repository and "--repo" not in command:
            command.extend(["--repo", self.repository])
        env = dict(os.environ)
        env.pop("GITHUB_TOKEN", None)
        env.pop("GH_TOKEN", None)
        # gh authentication is intentionally delegated to gh's configured
        # credential store / host auth. Do not copy tokens into worker state.
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=env,
                check=False,
            )
        except FileNotFoundError as exc:
            raise GitHubError("GitHub CLI (gh) is not installed") from exc
        except subprocess.TimeoutExpired as exc:
            raise GitHubError(f"GitHub CLI timed out after {self.timeout}s") from exc
        if check and result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise GitHubError(detail or f"gh exited with {result.returncode}")
        return result.stdout.strip()

    def status(self) -> dict:
        """Return authenticated GitHub identity and repository visibility."""
        raw = self._run(["auth", "status", "--hostname", "github.com"], check=False)
        return {"authenticated": "Logged in" in raw, "output": raw}

    def create_pull_request(
        self,
        *,
        title: str,
        body: str,
        head: str,
        base: str = "main",
        draft: bool = False,
    ) -> PullRequest:
        """Create a PR from an already-pushed branch."""
        args = [
            "pr",
            "create",
            "--title",
            title,
            "--body",
            body,
            "--head",
            head,
            "--base",
            base,
            "--json",
            "number,url,title",
        ]
        if draft:
            args.append("--draft")
        raw = self._run(args)
        try:
            data = json.loads(raw)
            return PullRequest(
                number=int(data["number"]),
                url=str(data["url"]),
                title=str(data["title"]),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise GitHubError(f"Unexpected gh pr create response: {raw[:500]}") from exc

    def view_pull_request(self, number: int) -> dict:
        """Return machine-readable PR metadata for review/audit."""
        raw = self._run(
            [
                "pr",
                "view",
                str(number),
                "--json",
                "number,url,title,state,isDraft,mergeable,reviewDecision,statusCheckRollup",
            ]
        )
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GitHubError(f"Unexpected gh pr view response: {raw[:500]}") from exc

    def merge_pull_request(self, number: int, *, squash: bool = True) -> str:
        """Merge an already-approved PR. Authorization remains caller-owned."""
        method = "squash" if squash else "merge"
        return self._run(["pr", "merge", str(number), f"--{method}", "--delete-branch"])
