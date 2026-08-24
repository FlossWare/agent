## Coding Agent (FlossWare)

FlossWare coding-agent-ai is an AI coding-agent execution/orchestration stack. Worker/arbiter execution uses the configured FlossWare model-routing layer.

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

- Workers use configured LLM providers to inspect repos, propose changes, and run tests
- Arbiter independently reviews changes with structured accept/reject decisions
- Rejection feeds actionable feedback back to the worker for retry
- With `model-router-ai` installed: uses the FlossWare routing stack (including policy, cost, latency, and failover controls as configured)
- Without `model-router-ai`: uses the built-in fallback router with multi-provider failover where available
- Supports Cohere v2 API natively alongside OpenAI-compatible endpoints

### Environment Variables

Configure one or more approved provider credentials. Model/provider selection is controlled by policy and may include free-tier, paid, local, or enterprise-approved providers.

Examples:
- `COHERE_API_KEY`
- `GROQ_API_KEY`
- `OPENROUTER_API_KEY`
- `CEREBRAS_API_KEY`
- `GEMINI_API_KEY`
- `HUGGINGFACE_API_KEY`

Provider credentials belong to the parent/router process and must not be exposed to worker subprocesses.
