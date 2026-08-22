## Personal Agent (FlossWare)

AI coding-agent using free LLM models only. Worker/arbiter loop for code changes.

### Quick Start

```python
from personal_agent import CodingAgent, Task, Decision

agent = CodingAgent(".")
result = await agent.run(Task(
    description="Fix the bug in auth.py",
    repo_path=".",
    commands=["pytest tests/"],
))

if result.decision == Decision.ACCEPT:
    print(result.final_diff)
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
- With model-router-ai installed: uses full decorator stack (Thompson Sampling, cost awareness, latency optimization)
- Without model-router-ai: falls back to built-in SimpleFreeRouter with multi-provider failover
- Supports Cohere v2 API natively alongside OpenAI-compatible endpoints

### Environment Variables

Set at least one API key for a free provider:
- `COHERE_API_KEY` (recommended — most reliable)
- `GROQ_API_KEY`
- `OPENROUTER_API_KEY`
- `CEREBRAS_API_KEY`
- `GEMINI_API_KEY`
- `HUGGINGFACE_API_KEY`

Multiple keys enables automatic failover across providers.
