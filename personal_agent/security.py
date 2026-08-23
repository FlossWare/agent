"""Security boundaries for agent execution.

Provides:
- Path confinement (no escape from workspace root)
- Command policy (argv-preferred execution, explicit allow/deny)
- Credential environment sanitization
- Optional secret redaction helpers
"""

from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence


class SecurityError(Exception):
    """Raised when a security policy is violated."""


# ---------------------------------------------------------------------------
# Path confinement
# ---------------------------------------------------------------------------

def resolve_in_workspace(workspace: Path, rel_path: str) -> Path:
    """Resolve *rel_path* under *workspace* and ensure it stays inside.

    Rejects absolute paths, ``..`` traversal, and paths that resolve
    outside the workspace (including via symlinks when the final target
    is outside).

    Returns the resolved absolute Path on success.
    Raises SecurityError on violation.
    """
    if not rel_path or not rel_path.strip():
        raise SecurityError("Empty path is not allowed")

    # Reject absolute paths early (POSIX and Windows-style)
    candidate = Path(rel_path)
    if candidate.is_absolute() or (len(rel_path) >= 2 and rel_path[1] == ":"):
        raise SecurityError(f"Absolute paths are not allowed: {rel_path!r}")

    # Normalize separators and reject null bytes / control chars
    if "\x00" in rel_path:
        raise SecurityError("Path contains null byte")

    workspace = workspace.resolve()
    # Join then resolve; resolve() follows symlinks
    full = (workspace / candidate).resolve()

    try:
        full.relative_to(workspace)
    except ValueError as exc:
        raise SecurityError(
            f"Path escapes workspace root: {rel_path!r} -> {full}"
        ) from exc

    return full


def is_path_inside(workspace: Path, target: Path) -> bool:
    """Return True if *target* is inside *workspace* after resolve."""
    try:
        target.resolve().relative_to(workspace.resolve())
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Command policy
# ---------------------------------------------------------------------------

# Commands that are always denied (basename match, case-insensitive on Windows
# but we assume POSIX). These are matched against the resolved executable name.
DENIED_COMMANDS = frozenset({
    "sudo", "su", "doas",
    "mkfs", "mkfs.ext4", "mkfs.xfs", "mkfs.btrfs",
    "fdisk", "parted", "gdisk",
    "shutdown", "reboot", "halt", "poweroff", "init",
    "iptables", "nft", "ufw",
    "useradd", "userdel", "usermod", "passwd", "chpasswd",
    "visudo",
    "mount", "umount",
    "dd",
    "nc", "ncat", "netcat",
    "socat",
    "tcpdump", "wireshark", "tshark",
    "strace", "gdb",  # can attach to other processes; deny by default
    "chmod", "chown", "chgrp",  # too easy to break isolation; allow via explicit policy later
    "curl", "wget", "http", "httpie",  # network is an explicit capability
    "ssh", "scp", "sftp", "rsync",
    "docker", "podman", "kubectl", "helm",
    "systemctl", "service",
    "crontab", "at",
    "bash", "sh", "zsh", "fish", "csh", "tcsh", "ksh",  # interactive shells
    "eval", "exec",
})

# Safe, common development commands (basename). Arguments are still validated.
ALLOWED_COMMANDS = frozenset({
    "echo", "printf", "true", "false", "test", "[",
    "cat", "head", "tail", "wc", "sort", "uniq", "cut", "tr", "tee",
    "grep", "egrep", "fgrep", "rg", "ag",
    "find", "ls", "dir", "file", "stat", "pwd", "basename", "dirname",
    "diff", "cmp", "md5sum", "sha256sum", "sha1sum",
    "git",
    "pytest", "python", "python3",  # needed for tests; see note below
    "pip", "pip3", "uv", "poetry", "tox", "nox",
    "mypy", "ruff", "flake8", "black", "isort", "pylint",
    "make", "cmake", "ninja",
    "npm", "npx", "yarn", "pnpm",
    "cargo", "go", "javac", "java", "mvn", "gradle",
    "gcc", "g++", "clang", "clang++", "cc",
    "rustc", "ruby", "bundle",
    "sleep", "date", "env", "printenv", "which", "type", "command",
    "mkdir", "touch", "cp", "mv", "rm", "ln",  # restricted further by args
    "tar", "gzip", "gunzip", "zip", "unzip",
    "sed", "awk",
})

# Patterns that indicate shell metacharacters / injection when present in a
# single command string that we would otherwise pass to shell=True.
SHELL_METACHAR_RE = re.compile(
    r"""[;|&`$(){}]|  # separators / substitution
        \$\(|         # command substitution
        `[^`]*`|      # backticks
        >\s*/|        # redirect to absolute
        >>\s*/|
        <\s*/|
        \|\s*(sh|bash|zsh|dash|ksh|csh|tcsh|python|perl|ruby)\b
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Additional substring denials for whole command lines (defense in depth).
DANGEROUS_SUBSTRINGS = (
    "rm -rf /", "rm -rf /*", "rm -rf ~", "rm -rf $HOME",
    ":(){ :|:& };:", "fork()",
    "> /dev/", ">> /dev/",
    "> /etc/", ">> /etc/",
    "chmod -R 777 /", "chown -R",
    "mkfs", "dd if=",
    "shutdown", "reboot", "halt", "poweroff",
    "kill -9 1", "kill -KILL 1",
    "| sh", "| bash", "| zsh",
    "sudo ", " su ",
    "nc -l", "ncat -l",
    "truncate -s 0",
    "shred ", "wipefs",
    "/etc/passwd", "/etc/shadow",
    "curl ", "wget ",  # network default-deny
)


@dataclass
class CommandPolicy:
    """Explicit policy for which commands a worker may execute."""

    allowed: frozenset[str] = ALLOWED_COMMANDS
    denied: frozenset[str] = DENIED_COMMANDS
    allow_network: bool = False
    allow_shell: bool = False  # if False, prefer argv and reject metacharacters
    extra_allowed: frozenset[str] = field(default_factory=frozenset)
    extra_denied: frozenset[str] = field(default_factory=frozenset)
    workspace: Path | None = None

    def effective_allowed(self) -> frozenset[str]:
        return self.allowed | self.extra_allowed

    def effective_denied(self) -> frozenset[str]:
        denied = self.denied | self.extra_denied
        if not self.allow_network:
            denied = denied | frozenset({"curl", "wget", "http", "httpie", "nc", "ncat", "netcat", "ssh", "scp"})
        return denied

    def check(self, cmd: str | Sequence[str]) -> list[str]:
        """Validate a command. Return argv list if allowed; raise SecurityError."""
        if isinstance(cmd, str):
            raw = cmd.strip()
            if not raw:
                raise SecurityError("Empty command")

            # Substring denials first (fast, covers classic patterns)
            lower = raw.lower()
            for s in DANGEROUS_SUBSTRINGS:
                if s.lower() in lower:
                    raise SecurityError(f"Denied dangerous pattern in command: {raw!r}")

            if not self.allow_shell and SHELL_METACHAR_RE.search(raw):
                raise SecurityError(
                    f"Shell metacharacters not allowed without allow_shell: {raw!r}"
                )

            try:
                argv = shlex.split(raw)
            except ValueError as exc:
                raise SecurityError(f"Could not parse command: {raw!r}") from exc
        else:
            argv = list(cmd)
            raw = " ".join(argv)

        if not argv:
            raise SecurityError("Empty argv")

        # Resolve executable name (basename only for policy)
        exe = Path(argv[0]).name.lower()

        denied = self.effective_denied()
        if exe in denied:
            raise SecurityError(f"Command is denied by policy: {exe!r}")

        allowed = self.effective_allowed()
        # If we have an allowlist, require membership. python/python3 are in
        # both lists historically; denied wins when in denied.
        if allowed and exe not in allowed:
            raise SecurityError(f"Command not in allowlist: {exe!r}")

        # Extra restrictions on destructive tools
        if exe in {"rm", "rmdir"}:
            self._check_rm_args(argv)
        if exe in {"chmod", "chown", "chgrp"}:
            raise SecurityError(f"{exe} is denied by default policy")

        # Working directory / path args: if workspace set, reject absolute
        # paths outside workspace for common file operands (best-effort).
        if self.workspace is not None:
            self._check_path_args(argv)

        return argv

    def _check_rm_args(self, argv: list[str]) -> None:
        joined = " ".join(argv)
        if re.search(r"(^|\s)/($|\s)", joined) or "/*" in joined or "/.." in joined:
            raise SecurityError(f"rm targeting filesystem root is denied: {argv!r}")
        if any(a in {"/", "/*", "~", "$HOME"} for a in argv[1:]):
            raise SecurityError(f"rm targeting sensitive path is denied: {argv!r}")

    def _check_path_args(self, argv: list[str]) -> None:
        assert self.workspace is not None
        for arg in argv[1:]:
            if arg.startswith("-"):
                continue
            # Only check args that look like paths
            if "/" not in arg and not arg.startswith("."):
                continue
            try:
                if Path(arg).is_absolute():
                    resolve_in_workspace(self.workspace, str(Path(arg).relative_to("/")))
            except (SecurityError, ValueError):
                # Absolute path outside workspace
                if Path(arg).is_absolute():
                    try:
                        resolve_in_workspace(self.workspace, arg.lstrip("/"))
                    except SecurityError:
                        # Still allow if the absolute path is actually under workspace
                        if not is_path_inside(self.workspace, Path(arg)):
                            raise SecurityError(
                                f"Command argument path outside workspace: {arg!r}"
                            )


DEFAULT_POLICY = CommandPolicy()


# ---------------------------------------------------------------------------
# Credential / environment isolation
# ---------------------------------------------------------------------------

# Environment variable names that must never be visible to the worker process.
PROVIDER_CREDENTIAL_VARS = frozenset({
    "GROQ_API_KEY",
    "CEREBRAS_API_KEY",
    "OPENROUTER_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "COHERE_API_KEY",
    "HUGGINGFACE_API_KEY",
    "HF_TOKEN",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SESSION_TOKEN",
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "GITLAB_TOKEN",
    "NPM_TOKEN",
    "PYPI_TOKEN",
    "TWINE_PASSWORD",
    "DOCKER_PASSWORD",
    "SSH_AUTH_SOCK",
    "SSH_AGENT_PID",
})

# Broader patterns for secret-looking env vars (matched case-insensitively).
SECRET_ENV_PATTERNS = (
    re.compile(r".*_API_KEY$", re.I),
    re.compile(r".*_SECRET$", re.I),
    re.compile(r".*_TOKEN$", re.I),
    re.compile(r".*_PASSWORD$", re.I),
    re.compile(r".*_PRIVATE_KEY$", re.I),
    re.compile(r".*SECRET_KEY$", re.I),
    re.compile(r"^AWS_.*", re.I),
)


def sanitize_worker_environ(
    base: dict[str, str] | None = None,
    *,
    extra_block: frozenset[str] | None = None,
) -> dict[str, str]:
    """Build an environment dict safe to pass to a coding worker subprocess.

    Provider and common secret variables are stripped. PATH, HOME, LANG,
    and similar operational vars are retained so tools can run.
    """
    src = dict(base if base is not None else os.environ)
    blocked = set(PROVIDER_CREDENTIAL_VARS)
    if extra_block:
        blocked |= set(extra_block)

    clean: dict[str, str] = {}
    for key, value in src.items():
        if key in blocked:
            continue
        if any(p.match(key) for p in SECRET_ENV_PATTERNS):
            continue
        clean[key] = value
    return clean


# ---------------------------------------------------------------------------
# Lightweight secret redaction (for logs / arbiter input)
# ---------------------------------------------------------------------------

_SECRET_VALUE_PATTERNS = [
    # Bearer / API key style
    re.compile(r"(?i)(bearer\s+)[a-z0-9\-._~+/]+=*"),
    re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)[^\s'\"&,]+"),
    re.compile(r"(?i)(secret\s*[=:]\s*)[^\s'\"&,]+"),
    re.compile(r"(?i)(password\s*[=:]\s*)[^\s'\"&,]+"),
    re.compile(r"(?i)(token\s*[=:]\s*)[^\s'\"&,]+"),
    # Common key prefixes
    re.compile(r"\b(sk-[A-Za-z0-9]{20,})\b"),
    re.compile(r"\b(ghp_[A-Za-z0-9]{20,})\b"),
    re.compile(r"\b(gho_[A-Za-z0-9]{20,})\b"),
    re.compile(r"\b(xox[baprs]-[A-Za-z0-9\-]{10,})\b"),
    re.compile(r"\b(AKIA[0-9A-Z]{16})\b"),
]


def redact_secrets(text: str, replacement: str = "***REDACTED***") -> str:
    """Best-effort redaction of common secret patterns from *text*."""
    if not text:
        return text
    out = text
    for pat in _SECRET_VALUE_PATTERNS:
        def _sub(m: re.Match, _pat=pat) -> str:
            # If pattern has a prefix group + secret, keep prefix
            if m.lastindex and m.lastindex >= 2:
                return m.group(1) + replacement
            # Prefix-style patterns with one group that is the prefix:
            # e.g. (bearer\s+)secret  -> group(1) is prefix
            g1 = m.group(1) if m.lastindex else ""
            if g1 and not _looks_like_secret(g1):
                return g1 + replacement
            return replacement
        out = pat.sub(_sub, out)
    return out


def _looks_like_secret(s: str) -> bool:
    """Heuristic: prefix groups are short words; secrets are long opaque tokens."""
    if len(s) >= 12 and any(c.isdigit() for c in s):
        return True
    if s.startswith(("sk-", "ghp_", "gho_", "xox", "AKIA")):
        return True
    return False
