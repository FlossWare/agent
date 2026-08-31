# Troubleshooting

User-facing guidance for common failures during the v0.1.0 dogfood phase.
Credentials must never be pasted into issues, logs, or chat.

## Debug mode

```bash
# Verbose logging from the CLI
pa -v "Fix the failing test" --repo .

# Equivalent via environment (if your wrapper exports it)
export PA_DEBUG=1
pa "Fix the failing test" --repo .
```

`-v` / `--verbose` sets the root logger to DEBUG. Use it when diagnosing
router timeouts, worktree failures, or unexpected REJECT loops.

## Common errors

### `ModuleNotFoundError: No module named 'resilience_ai'` (or similar)

Git dependencies were not installed into the active environment.

```bash
# Prefer the setup installer (Fedora Tier-1)
cd /path/to/coding-agent-setup && ./scripts/install.sh

# Or editable install from this repo
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
```

Confirm the active interpreter matches the venv that received the install:
`which python` / `which pa`.

### Credential / provider not found

Provider keys live in the **parent** process only (see [SECURITY.md](SECURITY.md)).
The worker never receives them.

1. Configure authentication via `coding-agent-setup` (`flossware-ai accounts --verify`).
2. Reuse an already-authenticated CLI session when the provider supports it.
3. Do not put secrets in `AGENTS.md`, `CLAUDE.md`, profiles, or the repo tree.

### Worktree leftover after interrupt

`Ctrl-C` during a run may leave a detached worktree under the repo’s git dir.

```bash
git worktree list
git worktree prune
# If a specific path remains:
git worktree remove --force /path/to/leftover-worktree
```

CodingAgent cleans worktrees on normal exit (success or hard-gate failure).
Interrupted processes may need a manual prune.

### Model router timeout

Network or provider latency exceeded the router budget.

- Retry with `-v` to see which provider/model was selected.
- Check provider status and rate limits outside this process.
- Reduce task scope or `--max-iter` while investigating.

### Arbiter rejection loop exhaustion (`max-iter`)

Default is 3 iterations (`--max-iter` / `-i`). After the limit, the last
decision is returned without further worker cycles.

- Read the final findings and reason in the CLI output (or `--json`).
- Tighten the task description; include failing test commands via `--commands`.
- Raise `--max-iter` only when the feedback is clearly converging.

### Permissions on generated instruction files

Generated `AGENTS.md` / `CLAUDE.md` content must remain secret-free. If the
agent cannot write them, check directory permissions and that the path is
inside the workspace (filesystem confinement rejects escapes).

## Cleanup commands

```bash
# Stale worktrees
git worktree list
git worktree prune

# Local editable install reset
pip uninstall coding-agent-ai -y
pip install -e '.[dev]'

# Managed FlossWare install (via setup repo)
./scripts/install.sh --reinstall
# or cleanup of managed state only:
./scripts/install.sh --clean
```

## Logs and verbosity

- Default level: INFO (`%(levelname)s: %(message)s` to stderr).
- Debug: `pa -v ...`.
- Structured output: `pa ... --json` for machine-readable results.

There is no separate log file by default; capture stderr when you need a
persistent trace.

## Related docs

- [SECURITY.md](SECURITY.md) — trust boundaries and credential isolation
- [COMMAND-POLICY.md](COMMAND-POLICY.md) — command allow/deny policy
- [SETUP.md](SETUP.md) — installation and environment
- [MIGRATION.md](MIGRATION.md) — personal-agent → coding-agent-ai rename
