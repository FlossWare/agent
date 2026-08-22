"""Repository inspection and modification utilities.

Provides the tools workers need to inspect files, search code,
read git state, run commands, and modify files in a repository.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from personal_agent.types import CommandResult, FileChange


class Repo:
    """Interface to a local git repository."""

    def __init__(self, path: str) -> None:
        self.path = Path(path).resolve()
        if not (self.path / ".git").exists():
            raise ValueError(f"Not a git repository: {self.path}")

    def read_file(self, rel_path: str) -> str:
        full = self.path / rel_path
        if not full.exists():
            raise FileNotFoundError(f"{rel_path} not found in {self.path}")
        return full.read_text()

    def write_file(self, rel_path: str, content: str) -> None:
        full = self.path / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)

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

    def git_status(self) -> str:
        return self.run_command("git status --short").stdout

    def git_diff(self, staged: bool = False) -> str:
        cmd = "git diff --staged" if staged else "git diff"
        return self.run_command(cmd).stdout

    def git_log(self, n: int = 10) -> str:
        return self.run_command(f"git log --oneline -n {n}").stdout

    def git_add(self, *files: str) -> CommandResult:
        if files:
            return self.run_command(f"git add {' '.join(files)}")
        return self.run_command("git add -A")

    def git_commit(self, message: str) -> CommandResult:
        return self.run_command(f"git commit -m {message!r}")

    def run_command(self, cmd: str, timeout: int = 120) -> CommandResult:
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                cwd=str(self.path),
                timeout=timeout,
            )
            return CommandResult(
                command=cmd,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        except subprocess.TimeoutExpired:
            return CommandResult(
                command=cmd,
                returncode=-1,
                stderr=f"Command timed out after {timeout}s",
            )
        except Exception as e:
            return CommandResult(
                command=cmd,
                returncode=-1,
                stderr=str(e),
            )

    def apply_changes(self, changes: list[FileChange]) -> list[CommandResult]:
        results = []
        for change in changes:
            if change.action == "delete":
                full = self.path / change.path
                if full.exists():
                    full.unlink()
                    results.append(CommandResult(command=f"delete {change.path}"))
            elif change.action in ("create", "modify"):
                self.write_file(change.path, change.content)
                results.append(CommandResult(command=f"{change.action} {change.path}"))
        return results

    def tree(self, max_depth: int = 3) -> str:
        lines = []
        self._tree_walk(self.path, "", 0, max_depth, lines)
        return "\n".join(lines[:200])

    def _tree_walk(self, path: Path, prefix: str, depth: int, max_depth: int, lines: list[str]) -> None:
        if depth >= max_depth:
            return
        try:
            entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
        except PermissionError:
            return
        for entry in entries:
            if entry.name.startswith(".") or entry.name == "__pycache__" or entry.name == "node_modules":
                continue
            lines.append(f"{prefix}{entry.name}")
            if entry.is_dir():
                self._tree_walk(entry, prefix + "  ", depth + 1, max_depth, lines)
