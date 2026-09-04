# Troubleshooting

User-facing guidance for common failures during the 0.1 dogfood phase.
Credentials must never be pasted into issues, logs, or chat.

## Debug mode

```bash
pa -v "Fix the failing test" --repo .
export PA_DEBUG=1
pa "Fix the failing test" --repo .
```

`-v` / `--verbose` sets the root logger to DEBUG. Use it when diagnosing router timeouts, worktree failures, or unexpected REJECT loops.

## Common errors

### `ModuleNotFoundError: No module named 'resilience_ai'` (or similar)

Git dependencies were not installed into the active environment.

```bash
cd /path/to/coding-agent-setup && ./scripts/install.sh
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
```

Confirm the active interpreter matches the environment that received the install: `which python` and `which pa`.

### Credential / provider not found

Provider keys live in the parent process only. The worker never receives them.

1. Configure authentication via `agent-setup` (`flossware-ai accounts --verify`).
2. Reuse an already-authenticated CLI session when supported.
3. Do not put secrets in `AGENTS.md`, `CLAUDE.md`, profiles, or the repository tree.

### Worktree leftover after interrupt

`Ctrl-C` during a run may leave a detached worktree under the repository's git directory.

```bash
git worktree list
git worktree prune
git worktree remove --force /path/to/leftover-worktree
```

Normal success and hard-gate failure paths clean up their worktrees. Interrupted processes may need manual pruning.

### Model router timeout

Network or provider latency exceeded the router budget. Retry with `-v`, check provider status/rate limits outside the process, and reduce task scope or `--max-iter` while investigating.

### Arbiter rejection loop exhaustion

The default is 3 iterations (`--max-iter` / `-i`). Read final findings with normal or `--json` output. Tighten the task description and include failing tests via `--commands`. Raise `--max-iter` only when feedback is clearly converging.

### Permissions on generated instruction files

Generated `AGENTS.md` / `CLAUDE.md` content must remain secret-free. Check directory permissions and ensure the path is inside the workspace; filesystem confinement rejects escapes.

## Cleanup commands

```bash
git worktree list
git worktree prune
pip uninstall agent-ai -y
pip install -e '.[dev]'
```

Managed installation cleanup remains the responsibility of `agent-setup`.

## Logs and verbosity

- Default level: INFO.
- Debug: `pa -v ...`.
- Structured output: `pa ... --json`.
- There is no separate log file by default; capture stderr for a persistent trace.

## Related docs

- [SECURITY.md](SECURITY.md)
- [COMMAND-POLICY.md](COMMAND-POLICY.md)
- [SETUP.md](SETUP.md)
- [MIGRATION.md](MIGRATION.md)
