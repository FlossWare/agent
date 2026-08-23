## Coding Agent

AI coding agent that uses free LLM models to investigate, modify, test, and review code changes.

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

### API Keys

Set one or more free provider keys (multiple enables automatic failover):
- `COHERE_API_KEY` - Cohere (command-a-03-2025, recommended)
- `GROQ_API_KEY` - Groq (qwen/qwen3.6-27b)
- `OPENROUTER_API_KEY` - OpenRouter (free-tier models)
- `CEREBRAS_API_KEY` - Cerebras (llama-3.3-70b)
- `GEMINI_API_KEY` - Google Gemini
- `HUGGINGFACE_API_KEY` - HuggingFace

### Python API

```python
from personal_agent import CodingAgent, Task, Decision

agent = CodingAgent("/path/to/repo")
result = await agent.run(Task(description="Fix the bug"))

if result.decision == Decision.ACCEPT:
    print(result.final_diff)
    print(result.commit_message)
```
