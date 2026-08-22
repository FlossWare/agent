## Personal Agent (FlossWare)

This project uses `personal-agent` for AI-assisted coding workflows with free models only.

### Quick Start

```python
from personal_agent import CodingAgent, Task

agent = CodingAgent(".")
result = await agent.run(Task(
    description="Fix the bug in auth.py",
    repo_path=".",
    commands=["pytest tests/"],
))
```

### CLI

```bash
pa "Review this repo for correctness" --repo . --max-iter 3
pa --investigate "What does this codebase do?" --repo .
pa "Fix failing tests" --repo . -c "pytest tests/" --commit
```

### Architecture

```
Task -> Worker (investigate/implement) -> Tests -> Arbiter (review) -> Accept/Reject -> Retry -> Commit
```

- Workers use free LLM models to inspect repos, propose changes, run tests
- Arbiter independently reviews changes with structured accept/reject decisions
- Rejection feeds actionable feedback back to the worker for retry
- Uses model-router-ai for free-model routing (Groq, Cerebras, OpenRouter, Gemini, Cohere)

### Environment Variables

Set at least one API key for a free provider:
- `GROQ_API_KEY`
- `CEREBRAS_API_KEY`
- `OPENROUTER_API_KEY`
- `GEMINI_API_KEY`
- `COHERE_API_KEY`
