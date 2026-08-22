# Cursor Integration for personal-agent

Use [personal-agent](https://github.com/sfloess/personal-agent) inside Cursor for AI-powered code review and implementation with free models.

## Setup

1. Install personal-agent:
   ```bash
   pip install git+https://github.com/sfloess/personal-agent.git
   ```

2. Set at least one free-tier provider key in your shell profile:
   ```bash
   export COHERE_API_KEY="your-key"    # Recommended — most reliable
   export GROQ_API_KEY="your-key"      # Fast inference
   ```

3. Copy `.cursorrules` to your project root:
   ```bash
   cp integrations/cursor/.cursorrules /path/to/your/project/.cursorrules
   ```

## Usage

### In Cursor Chat

Ask Cursor to use personal-agent:

- "Run pa review on my changes"
- "Use personal-agent to fix the auth bug"
- "Investigate the database module with pa"

### In Cursor Terminal

```bash
# Review current changes
pa --investigate "Review changes for correctness" --repo .

# Fix with worker/arbiter loop
pa "Fix the failing test" --repo . -c "pytest"

# Auto-commit on acceptance
pa "Add input validation" --repo . --commit
```

### In Cursor Composer

Reference the `.cursorrules` file. Cursor will use the rules to suggest personal-agent commands when appropriate.

## How It Works

1. **Worker** inspects your repo, plans changes, modifies files, runs tests
2. **Arbiter** independently reviews the worker's changes
3. If rejected, the worker retries with arbiter feedback
4. If accepted, changes are ready to commit

All LLM calls go through free-tier providers (Cohere, Groq, OpenRouter, Cerebras, Gemini). Multiple keys enable automatic failover. No paid API keys required.
