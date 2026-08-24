## Coding Agent

AI coding agent using free-tier LLM models for code review and implementation.

### Commands

```bash
# Full worker/arbiter loop
pa "Fix the failing test in test_auth.py" --repo . -c "pytest tests/"

# Investigation only (no changes)
pa --investigate "What are the main components?" --repo .

# Auto-commit on acceptance
pa "Add input validation" --repo . --commit

# JSON output for programmatic use
pa "Refactor the database module" --repo . --json
```

### Python API

All methods are async:

```python
import asyncio
from personal_agent import CodingAgent, Task, Decision

async def main():
    agent = CodingAgent(".")
    result = await agent.run(Task(
        description="Fix the bug",
        commands=["pytest tests/"],
    ))
    if result.decision == Decision.ACCEPT:
        print(result.final_diff)

asyncio.run(main())
```

### API Keys

Set at least one free-tier provider key:
- `COHERE_API_KEY` — Cohere (recommended — most reliable)
- `GROQ_API_KEY` — Groq (fast inference)
- `OPENROUTER_API_KEY` — OpenRouter (free-tier models)
- `CEREBRAS_API_KEY` — Cerebras
- `GEMINI_API_KEY` — Google Gemini

Set multiple keys for automatic failover. No paid API keys required.

### Workflow

1. Worker receives task, inspects repo, proposes changes, runs tests
2. Arbiter independently reviews changes (accept/reject with findings)
3. On rejection, worker retries with structured feedback
4. On acceptance, changes are ready to commit/PR
