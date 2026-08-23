"""Repository inspection and modification utilities.

Provides the tools workers need to inspect files, search code,
read git state, run commands, and modify files in a repository.

Security boundaries (see personal_agent.security):
- All path operations are confined to the workspace root.
- Commands are validated by CommandPolicy and preferably run as argv
  (not shell=True).
- Provider credentials are stripped from the subprocess environment.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Sequence

from personal_agent.security import (
    CommandPolicy,
    SecurityError,
    resolve_in_workspace,
    sanitize_worker_environ,
)
from personal_agent.types import CommandResult, FileChange

logger = logging.getLogger(__name__)


class Repo:
    """Interface to a local git repository with security boundaries."""

    def __init__(
        self,
        path: str,
        *,
        policy: CommandPolicy | None = None,
        scrub_credentials: bool = True,
    ) -> None:
        self.path = Path(path).resolve()
        git_marker = self.path / ".git"
        if not git_marker.exists():
            raise ValueError(f"Not a git repository: {self.path}")
        self.policy = policy or CommandPolicy(workspace=self.path)
        if self.policy.workspace is None:
            self.policy.workspace = self.path
        self.scrub_credentials = scrub_credentials

    # ------------------------------------------------------------------
    # Path-confined file operations
    # ------------------------------------------------------------------

    def _resolve(self, rel_path: str) -> Path:
        return resolve_in_workspace(self.path, rel_path)

    def read_file(self, rel_path: str) -> str:
        full = self._resolve(rel_path)
        if not full.exists():
            raise FileNotFoundError(f"{rel_path} not found in {self.path}")
        if not full.is_file():
            raise IsADirectoryError(f"{rel_path} is not a file")
        return full.read_text()

    def write_file(self, rel_path: str, content: str) -> None:
        full = self._resolve(rel_path)
        parent = full.parent
        try:
            parent.relative_to(self.path)
        except ValueError as exc:
            raise SecurityError(f"Parent path escapes workspace: {rel_path}") from exc
        parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)

    def delete_file(self, rel_path: str) -> None:
        full = self._resolve(rel_path)
        if full.exists() and full.is_file():
            full.unlink()

    def list_files(self, pattern: str = "**/*.py") -> list[str]:
        return sorted(
            str(p.relative_to(self.path))
            for p in self.path.glob(pattern)
            if ".git" not in p.parts
        )

    def grep(self, pattern: str, file_pattern: str = "*.py") -> list[tuple[str, int, str]]:
        """Search for a pattern in files. Returns (file, line_no, line)."""
        results = []
        for fpath in self.list_files(f"**/{file_pattern}"):
            try:
                for i, line in enumerate(self.read_file(fpath).splitlines(), 1):
                    if pattern in line:
                        results.append((fpath, i, line.strip()))
            except Exception:
                continue
        return results

    # ------------------------------------------------------------------
    # Git helpers (always go through policy)
    # ------------------------------------------------------------------

    def git_status(self) -> str:
        return self.run_command(["git", "status", "--short"]).stdout

    def git_diff(self, staged: bool = False) -> str:
        cmd = ["git", "diff", "--staged"] if staged else ["git", "diff"]
        return self.run_command(cmd).stdout

    def git_log(self, n: int = 10) -> str:
        return self.run_command(["git", "log", "--oneline", "-n", str(n)]).stdout

    def git_add(self, *files: str) -> CommandResult:
        if files:
            for f in files:
                self._resolve(f)
            return self.run_command(["git", "add", *files])
        return self.run_command(["git", "add", "-A"])

    def git_commit(self, message: str) -> CommandResult:
        return self.run_command(["git", "commit", "-m", message])

    # ------------------------------------------------------------------
    # Command execution under policy
    # ------------------------------------------------------------------

    def run_command(
        self,
        cmd: str | Sequence[str],
        timeout: int = 120,
        *,
        policy: CommandPolicy | None = None,
    ) -> CommandResult:
        """Run a command under CommandPolicy with credential-scrubbed env.

        Prefer passing an argv sequence. Strings are parsed with shlex and
        validated; shell metacharacters are rejected unless policy.allow_shell.
        """
        active = policy or self.policy
        display = cmd if isinstance(cmd, str) else " ".join(cmd)

        try:
            argv = active.check(cmd)
        except SecurityError as e:
            logger.warning("Command blocked by policy: %s (%s)", display, e)
            return CommandResult(
                command=display,
                returncode=-1,
                stderr=f"Blocked by security policy: {e}",
            )

        env = sanitize_worker_environ() if self.scrub_credentials else dict(os.environ)

        try:
            result = subprocess.run(
                argv,
                shell=False,
                capture_output=True,
                text=True,
                cwd=str(self.path),
                timeout=timeout,
                env=env,
            )
            return CommandResult(
                command=display,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        except subprocess.TimeoutExpired:
            return CommandResult(
                command=display,
                returncode=-1,
                stderr=f"Command timed out after {timeout}s",
            )
        except Exception as e:
            return CommandResult(
                command=display,
                returncode=-1,
                stderr=str(e),
            )

    def apply_changes(self, changes: list[FileChange]) -> list[CommandResult]:
        results = []
        for change in changes:
            try:
                if change.action == "delete":
                    self.delete_file(change.path)
                    results.append(CommandResult(command=f"delete {change.path}"))
                elif change.action in ("create", "modify"):
                    self.write_file(change.path, change.content)
                    results.append(CommandResult(command=f"{change.action} {change.path}"))
                else:
                    results.append(CommandResult(
                        command=f"unknown action {change.action} on {change.path}",
                        returncode=-1,
                        stderr=f"Unknown action: {change.action}",
                    ))
            except SecurityError as e:
                results.append(CommandResult(
                    command=f"{change.action} {change.path}",
                    returncode=-1,
                    stderr=f"Blocked by security policy: {e}",
                ))
        return results

    def tree(self, max_depth: int = 3) -> str:
        lines: list[str] = []
        self._tree_walk(self.path, "", 0, max_depth, lines)
        return "\n".join(lines[:200])

    def _tree_walk(
        self, path: Path, prefix: str, depth: int, max_depth: int, lines: list[str]
    ) -> None:
        if depth >= max_depth:
            return
        try:
            entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
        except PermissionError:
            return
        for entry in entries:
            if entry.name.startswith(".") or entry.name in ("__pycache__", "node_modules"):
                continue
            lines.append(f"{prefix}{entry.name}")
            if entry.is_dir():
                self._tree_walk(entry, prefix + "  ", depth + 1, max_depth, lines)

    # ------------------------------------------------------------------
    # Disposable worktrees (issue #4)
    # ------------------------------------------------------------------

    def create_worktree(self, branch_name: str | None = None) -> "Repo":
        """Create an isolated git worktree and return a Repo bound to it.

        The original working tree is left unchanged. Caller must call
        ``cleanup_worktree`` when done.
        """
        import uuid

        name = branch_name or f"pa-work-{uuid.uuid4().hex[:10]}"
        base = Path(tempfile.mkdtemp(prefix="pa-wt-"))
        wt_path = base / name

        result = subprocess.run(
            ["git", "worktree", "add", "--detach", str(wt_path), "HEAD"],
            cwd=str(self.path),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            shutil.rmtree(base, ignore_errors=True)
            raise RuntimeError(f"Failed to create worktree: {result.stderr}")

        child = Repo(
            str(wt_path),
            policy=CommandPolicy(
                allowed=self.policy.effective_allowed(),
                denied=self.policy.effective_denied(),
                allow_network=self.policy.allow_network,
                allow_shell=self.policy.allow_shell,
                workspace=wt_path.resolve(),
            ),
            scrub_credentials=self.scrub_credentials,
        )
        child._worktree_base = base  # type: ignore[attr-defined]
        child._worktree_parent = self  # type: ignore[attr-defined]
        child._worktree_path = wt_path  # type: ignore[attr-defined]
        return child

    def cleanup_worktree(self) -> None:
        """Remove a worktree created by ``create_worktree``."""
        parent: Repo | None = getattr(self, "_worktree_parent", None)
        wt_path: Path | None = getattr(self, "_worktree_path", None)
        base: Path | None = getattr(self, "_worktree_base", None)
        if parent is None or wt_path is None:
            return
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(wt_path)],
            cwd=str(parent.path),
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "worktree", "prune"],
            cwd=str(parent.path),
            capture_output=True,
            text=True,
        )
        if base is not None:
            shutil.rmtree(base, ignore_errors=True)

    def apply_diff_to(self, target: "Repo") -> CommandResult:
        """Apply the current unstaged diff of this repo onto *target*."""
        diff = self.git_diff()
        if not diff.strip():
            return CommandResult(command="apply_diff", stdout="(no changes)")
        proc = subprocess.run(
            ["git", "apply", "--whitespace=nowarn", "-"],
            input=diff,
            capture_output=True,
            text=True,
            cwd=str(target.path),
        )
        return CommandResult(
            command="git apply",
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )
