# coding-agent-ai

FlossWare coding-agent stack that composes [FlossWare](https://github.com/FlossWare) capabilities into a worker/arbiter loop for real software-engineering workflows.

**Free models only.** Uses Groq, Cerebras, OpenRouter, Gemini, Cohere, and HuggingFace — no paid API keys required.

## How It Works

```
Task → (isolated worktree) → Worker → Tests → Hard gates → Arbiter → Accept/Reject → Apply → Commit
```

1. **Worktree** — each run executes in a disposable git worktree so the primary checkout is untouched until acceptance
2. **Worker** receives a task, inspects the repository, formulates a plan, makes changes, runs tests
3. **Hard gates** force REJECT on test failures or security-policy violations (LLM cannot override)
4. **Arbiter** independently reviews changes with structured accept/reject decisions
5. If **rejected**, the worker receives actionable feedback and retries (up to N iterations)
6. If **accepted**, the worktree diff is applied to the primary tree and is ready for commit/PR

## Install

```bash
pip install git+https://github.com/FlossWare/coding-agent-ai.git
```

Or for development:

```bash
git clone https://github.com/FlossWare/coding-agent-ai.git
cd coding-agent-ai
pip install -e ".[dev]"
```

### Interactive Setup (TUI)

```bash
python3 scripts/setup.py
python3 scripts/setup.py --theme borland-3d
```

See [docs/SETUP.md](docs/SETUP.md). Non-interactive: `./scripts/install.sh --agent all --repo .`

## Quick Start

```bash
pa "Fix the failing test in test_auth.py" --repo . -c "pytest tests/"
pa --investigate "What are the main components?" --repo .
pa "Add input validation to the API" --repo . --commit
```

```python
import asyncio
from personal_agent import CodingAgent, Task, Decision

async def main():
    agent = CodingAgent("/path/to/repo")  # use_worktree=True by default
    result = await agent.run(Task(
        description="Fix the bug in auth.py",
        commands=["pytest tests/"],
        max_iterations=3,
    ))
    if result.decision == Decision.ACCEPT:
        print(result.final_diff)

asyncio.run(main())
```

## API Keys

| Provider | Environment Variable |
|----------|---------------------|
| Cohere | `COHERE_API_KEY` |
| Groq | `GROQ_API_KEY` |
| OpenRouter | `OPENROUTER_API_KEY` |
| Cerebras | `CEREBRAS_API_KEY` |
| Gemini | `GEMINI_API_KEY` |
| HuggingFace | `HUGGINGFACE_API_KEY` |

Provider keys stay in the router process only; worker subprocesses use a scrubbed environment. See [docs/SECURITY.md](docs/SECURITY.md).

## Safety

Full model: **[docs/SECURITY.md](docs/SECURITY.md)**

- **Command policy** — allowlist/denylist, argv execution, network as explicit capability
- **Filesystem confinement** — paths must resolve under workspace root
- **Credential isolation** — provider/repo/cloud/registry/SSH secrets stripped from worker env
- **Secret redaction** — tokens redacted from logs, prompts, feedback (`SecretRedactor`)
- **Hard verification gates** — tests/policy/syntax failures force REJECT; LLM cannot override
- **Disposable worktrees** — primary tree unchanged until accepted diff is applied

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## License

MIT
