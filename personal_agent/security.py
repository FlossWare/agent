"""Security boundaries for agent execution.

See docs/SECURITY.md for the trust model.
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
    PROVIDER = "provider"
    REPOSITORY = "repository"
    CLOUD = "cloud"
    PACKAGE_REGISTRY = "package_registry"
    SSH = "ssh"
    APPLICATION = "application"


# Paths under the workspace that workers must not write (hook / metadata abuse).
# Matched as path prefixes after normalize (forward slashes, lowercased).
FORBIDDEN_WRITE_PREFIXES = (
    ".git",
    ".git/",
)


def resolve_in_workspace(workspace: Path, rel_path: str) -> Path:
    """Resolve *rel_path* under *workspace* and ensure it stays inside."""
    if not rel_path or not str(rel_path).strip():
        raise SecurityError("Empty path is not allowed")

    rel_path = str(rel_path)
    candidate = Path(rel_path)
    if candidate.is_absolute() or (len(rel_path) >= 2 and rel_path[1] == ":"):
        raise SecurityError(f"Absolute paths are not allowed: {rel_path!r}")

    if "\x00" in rel_path:
        raise SecurityError("Path contains null byte")

    workspace = workspace.resolve()
    full = (workspace / candidate).resolve()

    try:
        full.relative_to(workspace)
    except ValueError as exc:
        raise SecurityError(
            f"Path escapes workspace root: {rel_path!r} -> {full}"
        ) from exc

    return full


def assert_writable_path(workspace: Path, rel_path: str) -> Path:
    """Like resolve_in_workspace, but also blocks forbidden write prefixes."""
    full = resolve_in_workspace(workspace, rel_path)
    rel = str(full.relative_to(workspace.resolve())).replace("\\", "/")
    lowered = rel.lower()
    for prefix in FORBIDDEN_WRITE_PREFIXES:
        p = prefix.lower().rstrip("/")
        if lowered == p or lowered.startswith(p + "/"):
            raise SecurityError(
                f"Writes under {prefix!r} are not allowed: {rel_path!r}"
            )
    return full


def is_path_inside(workspace: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(workspace.resolve())
        return True
    except ValueError:
        return False


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
    "tcpdump", "wireshark", "tshark",
    "strace", "gdb",
    "chmod", "chown", "chgrp",
    "docker", "podman", "kubectl", "helm",
    "systemctl", "service",
    "crontab", "at",
    "bash", "sh", "zsh", "fish", "csh", "tcsh", "ksh",
    "eval", "exec",
    "python2",
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

GIT_NETWORK_SUBCOMMANDS = frozenset({
    "clone", "fetch", "pull", "push", "ls-remote", "archive",
    "request-pull", "send-email",
})

# git submodule actions that contact remotes (URLs often only in .gitmodules)
GIT_SUBMODULE_NETWORK_ACTIONS = frozenset({
    "update", "sync", "add", "absorbgitdirs",
})

# git remote actions that contact remotes without a literal URL arg
GIT_REMOTE_NETWORK_ACTIONS = frozenset({
    "update", "prune",
})

SHELL_METACHAR_RE = re.compile(
    r"""[;|&`$(){}]|
        \$\(|
        `[^`]*`|
        >\s*/|
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
    "$(", "`",
    "${IFS}",
)

NETWORK_DANGEROUS_SUBSTRINGS = (
    "curl ", "wget ",
    "git clone", "git fetch", "git pull", "git push",
    "git ls-remote",
    "git submodule update", "git submodule sync", "git submodule add",
    "git remote update",
)

NETWORK_COMMANDS = frozenset({
    "curl", "wget", "http", "httpie", "nc", "ncat", "netcat",
    "ssh", "scp", "sftp", "rsync", "socat",
})

FIND_EXEC_FLAGS = frozenset({
    "-exec", "-execdir", "-ok", "-okdir", "-delete",
})

PATH_TAKING_SHORT_FLAGS = frozenset({
    "C",  # tar -C, make -C
    "t",  # cp -t
})


@dataclass
class CommandPolicy:
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
        denied = set(self.denied) | set(self.extra_denied)
        if self.allow_network:
            denied -= set(NETWORK_COMMANDS)
        else:
            denied |= set(NETWORK_COMMANDS)
        return frozenset(denied)

    def check(self, cmd: str | Sequence[str]) -> list[str]:
        if isinstance(cmd, str):
            raw = cmd.strip()
            if not raw:
                raise SecurityError("Empty command")

            lower = raw.lower()
            for s in DANGEROUS_SUBSTRINGS:
                if s.lower() in lower:
                    raise SecurityError(f"Denied dangerous pattern in command: {raw!r}")
            if not self.allow_network:
                for s in NETWORK_DANGEROUS_SUBSTRINGS:
                    if s.lower() in lower:
                        raise SecurityError(
                            f"Denied network pattern (allow_network=False): {raw!r}"
                        )

            if not self.allow_shell and SHELL_METACHAR_RE.search(raw):
                raise SecurityError(
                    f"Shell metacharacters not allowed without allow_shell: {raw!r}"
                )

            try:
                argv = shlex.split(raw)
            except ValueError as e:
                raise SecurityError(f"Could not parse command: {raw!r}") from e
        else:
            argv = [str(a) for a in cmd]
            raw = " ".join(argv)

        if not argv:
            raise SecurityError("Empty argv")

        exe_path = Path(argv[0])
        if "/" in argv[0] or argv[0].startswith("."):
            if self.workspace is not None:
                if not exe_path.is_absolute():
                    resolve_in_workspace(self.workspace, argv[0])
                elif not is_path_inside(self.workspace, exe_path):
                    raise SecurityError(
                        f"Executable path outside workspace: {argv[0]!r}"
                    )

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
        if exe == "find":
            self._check_find_args(argv)
        if exe == "git":
            self._check_git_args(argv)

        if self.workspace is not None:
            self._check_path_args(argv)

        return argv

    def _check_rm_args(self, argv: list[str]) -> None:
        joined = " ".join(argv)
        if re.search(r"(^|\s)/($|\s)", joined) or "/*" in joined or "/.." in joined:
            raise SecurityError(f"rm targeting filesystem root is denied: {argv!r}")
        if any(a in {"/", "/*", "~", "$HOME"} for a in argv[1:]):
            raise SecurityError(f"rm targeting sensitive path is denied: {argv!r}")

    def _check_find_args(self, argv: list[str]) -> None:
        for a in argv[1:]:
            if a in FIND_EXEC_FLAGS or a.startswith("-exec"):
                raise SecurityError(
                    f"find action {a!r} is denied (arbitrary command execution)"
                )

    def _check_git_args(self, argv: list[str]) -> None:
        # Skip global options to find the subcommand
        i = 1
        while i < len(argv):
            a = argv[i]
            if a in {"-C", "--git-dir", "--work-tree"}:
                i += 2
                continue
            if a.startswith("-"):
                i += 1
                continue
            break
        if i >= len(argv):
            return
        sub = argv[i].lower()
        rest = argv[i + 1:]

        if not self.allow_network:
            if sub in GIT_NETWORK_SUBCOMMANDS:
                raise SecurityError(
                    f"git {sub} requires network (allow_network=False)"
                )

            # submodule update/sync/add — network via .gitmodules URLs
            if sub == "submodule":
                action = self._next_git_action(rest)
                if action is None or action in GIT_SUBMODULE_NETWORK_ACTIONS:
                    # bare `git submodule` is status-like; allow.
                    # update/sync/add always need network capability.
                    if action in GIT_SUBMODULE_NETWORK_ACTIONS:
                        raise SecurityError(
                            f"git submodule {action} requires network "
                            f"(allow_network=False)"
                        )

            # remote update/prune contacts configured remotes
            if sub == "remote":
                action = self._next_git_action(rest)
                if action in GIT_REMOTE_NETWORK_ACTIONS:
                    raise SecurityError(
                        f"git remote {action} requires network "
                        f"(allow_network=False)"
                    )

            for a in rest:
                al = a.lower()
                if al.startswith((
                    "http://", "https://", "git://", "ssh://", "ftp://",
                    "git@", "ssh:",
                )):
                    raise SecurityError(
                        f"git remote URL denied when allow_network=False: {a!r}"
                    )

    @staticmethod
    def _next_git_action(args: list[str]) -> str | None:
        for a in args:
            if a.startswith("-"):
                continue
            return a.lower()
        return None

    def _check_path_args(self, argv: list[str]) -> None:
        assert self.workspace is not None
        i = 1
        while i < len(argv):
            arg = argv[i]

            if arg.startswith("--") and "=" in arg:
                self._validate_path_operand(arg.split("=", 1)[1])
                i += 1
                continue
            if arg.startswith("--"):
                i += 1
                continue

            if arg.startswith("-") and not arg.startswith("--"):
                body = arg[1:]
                for flag in PATH_TAKING_SHORT_FLAGS:
                    if body.startswith(flag) and len(body) > len(flag):
                        embedded = body[len(flag):].lstrip("=")
                        if embedded and ("/" in embedded or embedded.startswith(".")):
                            self._validate_path_operand(embedded)
                if body in PATH_TAKING_SHORT_FLAGS and i + 1 < len(argv):
                    self._validate_path_operand(argv[i + 1])
                    i += 2
                    continue
                i += 1
                continue

            if "/" in arg or arg.startswith("."):
                self._validate_path_operand(arg)
            i += 1

    def _validate_path_operand(self, arg: str) -> None:
        assert self.workspace is not None
        if not arg or arg.startswith("-"):
            return
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


CREDENTIAL_ENV_VARS: dict[str, CredentialClass] = {
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
    "AWS_SECRET_ACCESS_KEY": CredentialClass.CLOUD,
    "AWS_ACCESS_KEY_ID": CredentialClass.CLOUD,
    "AWS_SESSION_TOKEN": CredentialClass.CLOUD,
    "GITHUB_TOKEN": CredentialClass.REPOSITORY,
    "GH_TOKEN": CredentialClass.REPOSITORY,
    "GITLAB_TOKEN": CredentialClass.REPOSITORY,
    "NPM_TOKEN": CredentialClass.PACKAGE_REGISTRY,
    "PYPI_TOKEN": CredentialClass.PACKAGE_REGISTRY,
    "TWINE_PASSWORD": CredentialClass.PACKAGE_REGISTRY,
    "DOCKER_PASSWORD": CredentialClass.PACKAGE_REGISTRY,
    "SSH_AUTH_SOCK": CredentialClass.SSH,
    "SSH_AGENT_PID": CredentialClass.SSH,
}

PROVIDER_CREDENTIAL_VARS = frozenset(
    k for k, c in CREDENTIAL_ENV_VARS.items() if c == CredentialClass.PROVIDER
)

SAFE_ENV_ALLOWLIST = frozenset({
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "TERM", "LANG", "LC_ALL",
    "LC_CTYPE", "LC_MESSAGES", "LANGUAGE", "TZ", "TMPDIR", "TEMP", "TMP",
    "PWD", "OLDPWD", "SHLVL", "_",
    "PYTHONPATH", "PYTHONHOME", "PYTHONUNBUFFERED", "PYTHONDONTWRITEBYTECODE",
    "VIRTUAL_ENV", "CONDA_PREFIX", "CONDA_DEFAULT_ENV",
    "NODE_ENV", "npm_config_cache",
    "CI", "CONTINUOUS_INTEGRATION",
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy",
})

SECRET_ENV_PATTERNS = (
    re.compile(r".*_API_KEY$", re.I),
    re.compile(r".*_SECRET$", re.I),
    re.compile(r".*_TOKEN$", re.I),
    re.compile(r".*_PASSWORD$", re.I),
    re.compile(r".*_PRIVATE_KEY$", re.I),
    re.compile(r".*SECRET_KEY$", re.I),
    re.compile(r"^AWS_.*", re.I),
    re.compile(r".*_KEY$", re.I),
    re.compile(r".*WEBHOOK.*", re.I),
    re.compile(r".*CONN.*STRING.*", re.I),
    re.compile(r".*DATABASE_URL.*", re.I),
)


def sanitize_worker_environ(
    base: dict[str, str] | None = None,
    *,
    extra_block: frozenset[str] | None = None,
    extra_allow: frozenset[str] | None = None,
) -> dict[str, str]:
    src = dict(base if base is not None else os.environ)
    blocked = set(CREDENTIAL_ENV_VARS.keys())
    if extra_block:
        blocked |= set(extra_block)

    allow = set(SAFE_ENV_ALLOWLIST)
    if extra_allow:
        allow |= set(extra_allow)

    clean: dict[str, str] = {}
    for key, value in src.items():
        if key in blocked:
            continue
        if any(p.match(key) for p in SECRET_ENV_PATTERNS):
            continue
        if key not in allow:
            continue
        clean[key] = value
    return clean


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
    re.compile(r"\b(AIza[0-9A-Za-z\-_]{35})\b"),
    re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?"
        r"-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        re.DOTALL,
    ),
]


@dataclass
class SecretRedactor:
    enabled: bool = True
    replacement: str = "***REDACTED***"
    patterns: list[re.Pattern[str]] = field(
        default_factory=lambda: list(_DEFAULT_SECRET_PATTERNS)
    )

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
    if replacement != _DEFAULT_REDACTOR.replacement:
        return SecretRedactor(replacement=replacement).redact(text)
    return _DEFAULT_REDACTOR.redact(text)


def _looks_like_secret(s: str) -> bool:
    if len(s) >= 12 and any(c.isdigit() for c in s):
        return True
    if s.startswith(("sk-", "ghp_", "gho_", "ghu_", "ghs_", "xox", "AKIA", "AIza")):
        return True
    return False
