# OpenCode / Codex Integration for personal-agent

Use [personal-agent](https://github.com/FlossWare/personal-agent) with OpenCode or Codex for AI-powered code review and implementation with free models.

## Setup

1. Install personal-agent:
   ```bash
   pip install git+https://github.com/FlossWare/personal-agent.git
   ```

2. Set at least one free-tier provider key:
   ```bash
   export COHERE_API_KEY="your-key"    # Recommended — most reliable
   export GROQ_API_KEY="your-key"      # Fast inference
   ```

3. Copy integration files to your project:
   ```bash
   cp integrations/opencode/AGENTS.md /path/to/your/project/AGENTS.md
   cp integrations/opencode/.opencode.yaml /path/to/your/project/.opencode.yaml
   ```

## Usage

### With OpenCode

OpenCode reads `AGENTS.md` for agent instructions. Ask it to:

- "Use personal-agent to review my changes"
- "Run pa to fix the authentication bug"
- "Investigate the API module with personal-agent"

### With Codex CLI

```bash
# Review changes
pa --investigate "Review my changes for correctness" --repo .

# Fix an issue
pa "Fix the null pointer in user_service.py" --repo . -c "pytest"

# Full JSON output
pa "Add retry logic to API calls" --repo . --json
```

## Environment Variables

Set at least one (all are free-tier access):
- `COHERE_API_KEY` — Cohere (recommended — most reliable)
- `GROQ_API_KEY` — Groq (fast inference)
- `OPENROUTER_API_KEY` — OpenRouter (free-tier models)
- `CEREBRAS_API_KEY` — Cerebras
- `GEMINI_API_KEY` — Google Gemini

Set multiple keys for automatic failover. No paid API keys required.

## How It Works

Worker investigates → proposes changes → runs tests → arbiter reviews → accept/reject → retry → commit. All using free-tier LLM models with automatic provider failover.
