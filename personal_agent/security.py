"""Security boundaries for agent execution.

Provides:
- Path confinement (no escape from workspace root)
- Command policy (argv-preferred execution, explicit allow/deny)
- Credential environment sanitization by class
- Configurable secret redaction

Trust model
-----------
The coding worker is untrusted relative to the host. It may only:

1. Read/write paths that resolve inside the assigned workspace root.
2. Execute commands allowed by CommandPolicy, as argv (shell=False).
3. See an environment with provider and other secret credentials removed.

Provider API keys are owned exclusively by the router/provider layer in the
parent process. They must never be injected into worker subprocesses.
Network access is an explicit capability (CommandPolicy.allow_network),
not an implicit property of the environment.
"""

from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Sequence


class SecurityError(Exception):
    """Raised when a security policy is violated."""


class CredentialClass(str, Enum):
    """Classification of secrets the agent may encounter."""

    PROVIDER = "provider"  # LLM API keys — router only
    REPOSITORY = "repository"  # git/host tokens (GITHUB_TOKEN, etc.)
    CLOUD = "cloud"  # AWS/GCP/Azure credentials
    PACKAGE_REGISTRY = "package_registry"  # npm/pypi/docker tokens
    SSH = "ssh"  # agent sockets / keys
    APPLICATION = "application"  # app-specific secrets in env/files


# ---------------------------------------------------------------------------
# Path confinement
# ---------------------------------------------------------------------------

def resolve_in_workspace(workspace: Path, rel_path: str) -> Path:
    """Resolve *rel_path* under *workspace* and ensure it stays inside.

    Rejects absolute paths, ``..`` traversal, null bytes, and paths that
    resolve outside the workspace (including via symlinks).
    """
    if not rel_path or not str(rel_path).strip():
        raise SecurityError("Empty path is not allowed")

    rel_path = str(rel_path)
    candidate = Path(rel_path)
    if candidate.is_absolute() or (len(rel_path) >= 2 and rel_path[1] == ":"):
        raise SecurityError(f"Absolute paths are not allowed: {rel_path!r}")

    if "\x00" in rel_path:
        raise SecurityError("Path contains null byte")

    # Reject any explicit .. segment before resolve (defense in depth)
    parts = candidate.parts
    if ".." in parts:
        # Still allow resolve check — but fail fast on clear traversal intent
        pass

    workspace = workspace.resolve()
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
    "strace", "gdb",
    "chmod", "chown", "chgrp",
    "curl", "wget", "http", "httpie",
    "ssh", "scp", "sftp", "rsync",
    "docker", "podman", "kubectl", "helm",
    "systemctl", "service",
    "crontab", "at",
    "bash", "sh", "zsh", "fish", "csh", "tcsh", "ksh",
    "eval", "exec",
    "python2",  # prefer explicit python3
})

ALLOWED_COMMANDS = frozenset({
    "echo", "printf", "true", "false", "test", "[",
    "cat", "head", "tail", "wc", "sort", "uniq", "cut", "tr", "tee",
    "grep", "egrep", "fgrep", "rg", "ag",
    "find", "ls", "dir", "file", "stat", "pwd", "basename", "dirname",
    "diff", "cmp", "md5sum", "sha256sum", "sha1sum",
    "git",
    "pytest", "python", "python3",
    "pip", "pip3", "uv", "poetry", "tox", "nox",
    "mypy", "ruff", "flake8", "black", "isort", "pylint",
    "make", "cmake", "ninja",
    "npm", "npx", "yarn", "pnpm",
    "cargo", "go", "javac", "java", "mvn", "gradle",
    "gcc", "g++", "clang", "clang++", "cc",
    "rustc", "ruby", "bundle",
    "sleep", "date", "env", "printenv", "which", "type", "command",
    "mkdir", "touch", "cp", "mv", "rm", "ln",
    "tar", "gzip", "gunzip", "zip", "unzip",
    "sed", "awk",
})

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
    "curl ", "wget ",
    "$(", "`",  # command substitution markers
    "${IFS}",
)

NETWORK_COMMANDS = frozenset({
    "curl", "wget", "http", "httpie", "nc", "ncat", "netcat",
    "ssh", "scp", "sftp", "rsync", "socat",
})


@dataclass
class CommandPolicy:
    """Explicit policy for which commands a worker may execute.

    Network is an explicit capability: set allow_network=True to permit
    tools in NETWORK_COMMANDS (they remain subject to path rules).
    """

    allowed: frozenset[str] = ALLOWED_COMMANDS
    denied: frozenset[str] = DENIED_COMMANDS
    allow_network: bool = False
    allow_shell: bool = False
    extra_allowed: frozenset[str] = field(default_factory=frozenset)
    extra_denied: frozenset[str] = field(default_factory=frozenset)
    workspace: Path | None = None

    def effective_allowed(self) -> frozenset[str]:
        allowed = self.allowed | self.extra_allowed
        if self.allow_network:
            allowed = allowed | NETWORK_COMMANDS
        return allowed

    def effective_denied(self) -> frozenset[str]:
        denied = self.denied | self.extra_denied
        if not self.allow_network:
            denied = denied | NETWORK_COMMANDS
        return denied

    def check(self, cmd: str | Sequence[str]) -> list[str]:
        """Validate a command. Return argv list if allowed; raise SecurityError."""
        if isinstance(cmd, str):
            raw = cmd.strip()
            if not raw:
                raise SecurityError("Empty command")

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
            argv = [str(a) for a in cmd]
            raw = " ".join(argv)

        if not argv:
            raise SecurityError("Empty argv")

        # Reject path-like executable that tries to escape
        exe_path = Path(argv[0])
        if "/" in argv[0] or argv[0].startswith("."):
            if self.workspace is not None:
                try:
                    if not exe_path.is_absolute():
                        resolve_in_workspace(self.workspace, argv[0])
                    elif not is_path_inside(self.workspace, exe_path):
                        raise SecurityError(
                            f"Executable path outside workspace: {argv[0]!r}"
                        )
                except SecurityError:
                    raise

        exe = exe_path.name.lower()

        denied = self.effective_denied()
        if exe in denied:
            raise SecurityError(f"Command is denied by policy: {exe!r}")

        allowed = self.effective_allowed()
        if allowed and exe not in allowed:
            raise SecurityError(f"Command not in allowlist: {exe!r}")

        if exe in {"rm", "rmdir"}:
            self._check_rm_args(argv)
        if exe in {"chmod", "chown", "chgrp"}:
            raise SecurityError(f"{exe} is denied by default policy")

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
            if arg.startswith("-") and not arg.startswith("--"):
                # short flags; skip pure flags but check --file=path below
                if "=" not in arg:
                    continue
            if arg.startswith("--") and "=" in arg:
                arg = arg.split("=", 1)[1]
            if arg.startswith("-"):
                continue
            if "/" not in arg and not arg.startswith("."):
                continue
            p = Path(arg)
            if p.is_absolute():
                if not is_path_inside(self.workspace, p):
                    raise SecurityError(
                        f"Command argument path outside workspace: {arg!r}"
                    )
            else:
                try:
                    resolve_in_workspace(self.workspace, arg)
                except SecurityError:
                    raise SecurityError(
                        f"Command argument path outside workspace: {arg!r}"
                    )


DEFAULT_POLICY = CommandPolicy()


# ---------------------------------------------------------------------------
# Credential / environment isolation
# ---------------------------------------------------------------------------

# Explicit map of env var -> credential class for documentation and tests.
CREDENTIAL_ENV_VARS: dict[str, CredentialClass] = {
    # Provider (LLM)
    "GROQ_API_KEY": CredentialClass.PROVIDER,
    "CEREBRAS_API_KEY": CredentialClass.PROVIDER,
    "OPENROUTER_API_KEY": CredentialClass.PROVIDER,
    "GEMINI_API_KEY": CredentialClass.PROVIDER,
    "GOOGLE_API_KEY": CredentialClass.PROVIDER,
    "COHERE_API_KEY": CredentialClass.PROVIDER,
    "HUGGINGFACE_API_KEY": CredentialClass.PROVIDER,
    "HF_TOKEN": CredentialClass.PROVIDER,
    "OPENAI_API_KEY": CredentialClass.PROVIDER,
    "ANTHROPIC_API_KEY": CredentialClass.PROVIDER,
    "AZURE_OPENAI_API_KEY": CredentialClass.PROVIDER,
    # Cloud
    "AWS_SECRET_ACCESS_KEY": CredentialClass.CLOUD,
    "AWS_ACCESS_KEY_ID": CredentialClass.CLOUD,
    "AWS_SESSION_TOKEN": CredentialClass.CLOUD,
    # Repository host
    "GITHUB_TOKEN": CredentialClass.REPOSITORY,
    "GH_TOKEN": CredentialClass.REPOSITORY,
    "GITLAB_TOKEN": CredentialClass.REPOSITORY,
    # Package registries
    "NPM_TOKEN": CredentialClass.PACKAGE_REGISTRY,
    "PYPI_TOKEN": CredentialClass.PACKAGE_REGISTRY,
    "TWINE_PASSWORD": CredentialClass.PACKAGE_REGISTRY,
    "DOCKER_PASSWORD": CredentialClass.PACKAGE_REGISTRY,
    # SSH
    "SSH_AUTH_SOCK": CredentialClass.SSH,
    "SSH_AGENT_PID": CredentialClass.SSH,
}

PROVIDER_CREDENTIAL_VARS = frozenset(
    k for k, c in CREDENTIAL_ENV_VARS.items() if c == CredentialClass.PROVIDER
)

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

    Strips all known credential classes and pattern-matched secret names.
    PATH, HOME, LANG, and similar operational vars are retained.
    """
    src = dict(base if base is not None else os.environ)
    blocked = set(CREDENTIAL_ENV_VARS.keys())
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
# Secret redaction
# ---------------------------------------------------------------------------

_DEFAULT_SECRET_PATTERNS = [
    re.compile(r"(?i)(bearer\s+)[a-z0-9\-._~+/]+=*"),
    re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)[^\s'\"&,]+"),
    re.compile(r"(?i)(secret\s*[=:]\s*)[^\s'\"&,]+"),
    re.compile(r"(?i)(password\s*[=:]\s*)[^\s'\"&,]+"),
    re.compile(r"(?i)(token\s*[=:]\s*)[^\s'\"&,]+"),
    re.compile(r"\b(sk-[A-Za-z0-9]{20,})\b"),
    re.compile(r"\b(ghp_[A-Za-z0-9]{20,})\b"),
    re.compile(r"\b(gho_[A-Za-z0-9]{20,})\b"),
    re.compile(r"\b(ghu_[A-Za-z0-9]{20,})\b"),
    re.compile(r"\b(ghs_[A-Za-z0-9]{20,})\b"),
    re.compile(r"\b(xox[baprs]-[A-Za-z0-9\-]{10,})\b"),
    re.compile(r"\b(AKIA[0-9A-Z]{16})\b"),
    re.compile(r"\b(AIza[0-9A-Za-z\-_]{35})\b"),  # Google API keys
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.DOTALL),
]


@dataclass
class SecretRedactor:
    """Configurable secret redaction.

    Set enabled=False only in trusted diagnostic environments.
    """

    enabled: bool = True
    replacement: str = "***REDACTED***"
    patterns: list[re.Pattern[str]] = field(default_factory=lambda: list(_DEFAULT_SECRET_PATTERNS))

    def redact(self, text: str) -> str:
        if not self.enabled or not text:
            return text
        out = text
        for pat in self.patterns:
            def _sub(m: re.Match, _pat=pat) -> str:
                if m.lastindex and m.lastindex >= 1:
                    g1 = m.group(1)
                    if g1 and not _looks_like_secret(g1):
                        return g1 + self.replacement
                return self.replacement
            out = pat.sub(_sub, out)
        return out


_DEFAULT_REDACTOR = SecretRedactor()


def redact_secrets(text: str, replacement: str = "***REDACTED***") -> str:
    """Best-effort redaction of common secret patterns from *text*."""
    if replacement != _DEFAULT_REDACTOR.replacement:
        return SecretRedactor(replacement=replacement).redact(text)
    return _DEFAULT_REDACTOR.redact(text)


def _looks_like_secret(s: str) -> bool:
    if len(s) >= 12 and any(c.isdigit() for c in s):
        return True
    if s.startswith(("sk-", "ghp_", "gho_", "ghu_", "ghs_", "xox", "AKIA", "AIza")):
        return True
    return False
