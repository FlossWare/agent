## Personal Agent Integration

This project uses [personal-agent](https://github.com/sfloess/personal-agent) for AI-assisted code review and implementation using free LLM models.

### Prerequisites

```bash
pip install git+https://github.com/sfloess/personal-agent.git
```

Set at least one free provider key:
- `COHERE_API_KEY` (recommended)
- `GROQ_API_KEY`
- `OPENROUTER_API_KEY`
- `CEREBRAS_API_KEY`
- `GEMINI_API_KEY`

### Skills

Use these slash commands during a Claude Code session:

- `/pa-review` — Run an independent arbiter review of your current changes
- `/pa-fix` — Worker/arbiter loop to fix a specific issue
- `/pa-investigate` — Investigate the codebase without making changes

### Workflows

**Review before committing:**
```
You: "Review my staged changes before I commit"
→ Claude runs: pa --investigate "Review staged changes for correctness" --repo .
→ Returns structured findings with severity levels
```

**Fix a failing test:**
```
You: "Fix the failing test in test_auth.py"
→ Claude runs: pa "Fix the failing test in test_auth.py" --repo . -c "pytest tests/test_auth.py"
→ Worker investigates, proposes fix, arbiter reviews, retries if needed
```

**Investigate architecture:**
```
You: "What does the billing module do?"
→ Claude runs: pa --investigate "Explain the billing module architecture" --repo .
→ Returns plan and findings without modifying files
```

### Python API

```python
from personal_agent import CodingAgent, Task, Decision

agent = CodingAgent(".")
result = await agent.run(Task(
    description="Fix the bug in auth.py",
    commands=["pytest tests/"],
))

if result.decision == Decision.ACCEPT:
    print(result.final_diff)
```

### Pre-commit Hook

Copy `hooks/pre-commit` to `.git/hooks/pre-commit` to automatically review staged changes before each commit. The hook runs in investigation mode and warns on high-severity findings without blocking the commit.

### Configuration

All configuration is via environment variables. Set multiple provider keys for automatic failover.
