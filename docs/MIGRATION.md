# Migration: personal-agent → coding-agent-ai

## What changed

| Item | Old | New |
|------|-----|-----|
| GitHub repository | `FlossWare/personal-agent` | `FlossWare/coding-agent-ai` |
| Distribution / project name | `personal-agent` | `coding-agent-ai` |
| Install URL | `git+https://github.com/FlossWare/personal-agent.git` | `git+https://github.com/FlossWare/coding-agent-ai.git` |
| Python import package | `personal_agent` | `personal_agent` (unchanged in this release) |
| CLI entry point | `pa` | `pa` (unchanged) |

GitHub redirects `personal-agent` → `coding-agent-ai` for a period after the
repository rename. Prefer the new URL in all new documentation and CI.

## Upgrade

```bash
pip uninstall personal-agent -y
pip install git+https://github.com/FlossWare/coding-agent-ai.git
```

Development checkout:

```bash
git clone https://github.com/FlossWare/coding-agent-ai.git
cd coding-agent-ai
pip install -e ".[dev]"
```

## Related projects

- `coding-agent-setup` — environment/configuration for coding agents
- `coding-agent-ai` — execution/orchestration (this repository)

## Residual

The import path remains `personal_agent` to avoid a breaking Python API change
in the same release as the repository rename. A future issue may introduce
`coding_agent` (or similar) with a deprecation shim.
