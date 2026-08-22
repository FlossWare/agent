# OpenCode / Codex Integration for personal-agent

Use [personal-agent](https://github.com/sfloess/personal-agent) with OpenCode or Codex for AI-powered code review and implementation with free models.

## Setup

1. Install personal-agent:
   ```bash
   pip install git+https://github.com/sfloess/personal-agent.git
   ```

2. Set at least one free provider key:
   ```bash
   export COHERE_API_KEY="your-key"
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
pa --investigate "Review my changes" --repo .

# Fix an issue
pa "Fix the null pointer in user_service.py" --repo . -c "pytest"

# Full JSON output
pa "Add retry logic to API calls" --repo . --json
```

## How It Works

Worker investigates → proposes changes → runs tests → arbiter reviews → accept/reject → retry → commit. All using free LLM models with automatic provider failover.
