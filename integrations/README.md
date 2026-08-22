# Agent Integrations

Ready-to-use configurations for integrating [personal-agent](https://github.com/sfloess/personal-agent) with popular AI coding agents.

## Supported Agents

| Agent | Directory | Key Files | Status |
|-------|-----------|-----------|--------|
| [Claude Code](https://claude.ai/code) | `claude-code/` | `CLAUDE.md`, skills, pre-commit hook | Full integration |
| [Cursor](https://cursor.com) | `cursor/` | `.cursorrules` | Rules-based |
| [OpenCode](https://github.com/opencode-ai/opencode) / Codex | `opencode/` | `AGENTS.md`, `.opencode.yaml` | Agent instructions |

## Quick Setup

### Claude Code

```bash
# Copy CLAUDE.md and skills to your project
cp integrations/claude-code/CLAUDE.md /path/to/project/CLAUDE.md
cp -r integrations/claude-code/skills /path/to/project/.claude/skills/

# Optional: install pre-commit hook
cp integrations/claude-code/hooks/pre-commit /path/to/project/.git/hooks/pre-commit
chmod +x /path/to/project/.git/hooks/pre-commit
```

Then use `/pa-review`, `/pa-fix`, or `/pa-investigate` in Claude Code.

### Cursor

```bash
cp integrations/cursor/.cursorrules /path/to/project/.cursorrules
```

Ask Cursor: "Run pa review on my changes" or use the terminal.

### OpenCode / Codex

```bash
cp integrations/opencode/AGENTS.md /path/to/project/AGENTS.md
cp integrations/opencode/.opencode.yaml /path/to/project/.opencode.yaml
```

Ask OpenCode: "Use personal-agent to fix the bug."

## Prerequisites

All integrations require:

1. **personal-agent installed:**
   ```bash
   pip install git+https://github.com/sfloess/personal-agent.git
   ```

2. **At least one free-tier provider API key:**
   ```bash
   export COHERE_API_KEY="your-key"    # Recommended — most reliable
   export GROQ_API_KEY="your-key"      # Fast inference
   export OPENROUTER_API_KEY="your-key"
   ```

   All listed providers offer free-tier access — no paid API keys required. Set multiple keys for automatic failover between providers.

## Common Commands

These work from any agent's terminal:

```bash
# Review current changes
pa --investigate "Review changes for correctness" --repo .

# Fix a specific issue
pa "Fix the failing test" --repo . -c "pytest tests/"

# Auto-commit on acceptance
pa "Add input validation" --repo . --commit

# JSON output for programmatic use
pa "Refactor the module" --repo . --json
```
