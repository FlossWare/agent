## Coding Agent

FlossWare coding-agent-ai uses configured LLM providers to investigate, modify, test, and review code changes. Model selection is controlled by the FlossWare routing/policy layer.

### Usage

```bash
# Full worker/arbiter loop
pa "Fix the failing test in test_auth.py" --repo . -c "pytest tests/"

# Investigation only
pa --investigate "What are the main components?" --repo .

# With auto-commit on acceptance
pa "Add input validation to the API" --repo . --commit
```

### How It Works

1. **Worker** receives the task and inspects the repository
2. **Worker** proposes a plan, makes changes, runs tests
3. **Arbiter** independently reviews changes against the original task
4. If **rejected**, worker receives structured feedback and retries
5. If **accepted**, changes are ready for commit/PR

### Provider Credentials

Configure one or more provider credentials supported by the installed routing layer. Provider choice is policy-driven and may include free-tier, paid, local, or enterprise-approved providers. Never expose provider credentials to the worker environment.

Examples:
- `COHERE_API_KEY`
- `GROQ_API_KEY`
- `OPENROUTER_API_KEY`
- `CEREBRAS_API_KEY`
- `GEMINI_API_KEY`
- `HUGGINGFACE_API_KEY`

Multiple configured providers can enable automatic failover when supported by the router.

### Python API

```python
from personal_agent import CodingAgent, Task, Decision

agent = CodingAgent("/path/to/repo")
result = await agent.run(Task(description="Fix the bug"))

if result.decision == Decision.ACCEPT:
    print(result.final_diff)
    print(result.commit_message)
```
