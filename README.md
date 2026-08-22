# personal-agent

Personal AI coding-agent stack that composes [FlossWare](https://github.com/FlossWare) capabilities into a worker/arbiter loop for real software-engineering workflows.

**Free models only.** Uses Groq, Cerebras, OpenRouter, Gemini, Cohere, and HuggingFace — no paid API keys required.

## How It Works

```
Task → Worker (investigate/implement) → Tests → Arbiter (review) → Accept/Reject → Retry → Commit
```

1. **Worker** receives a task, inspects the repository, formulates a plan, makes changes, runs tests
2. **Arbiter** independently reviews changes with structured accept/reject decisions
3. If **rejected**, the worker receives actionable feedback and retries (up to N iterations)
4. If **accepted**, changes are ready for commit/PR

## Install

```bash
pip install git+https://github.com/FlossWare/personal-agent.git
```

Or for development:

```bash
git clone https://github.com/FlossWare/personal-agent.git
cd personal-agent
pip install -e ".[dev]"
```

## Quick Start

### CLI

```bash
# Full worker/arbiter loop
pa "Fix the failing test in test_auth.py" --repo . -c "pytest tests/"

# Investigation only (no changes)
pa --investigate "What are the main components?" --repo .

# Auto-commit on acceptance
pa "Add input validation to the API" --repo . --commit

# JSON output for programmatic use
pa "Refactor the database module" --repo . --json
```

### Python API

```python
from personal_agent import CodingAgent, Task, Decision

agent = CodingAgent("/path/to/repo")
result = await agent.run(Task(
    description="Fix the bug in auth.py",
    commands=["pytest tests/"],
    max_iterations=3,
))

if result.decision == Decision.ACCEPT:
    print(result.final_diff)
    print(result.commit_message)
```

### Investigation Only

```python
result = await agent.investigate_only(Task(
    description="What does this codebase do?",
))
print(result.plan)
print(result.findings)
```

## API Keys

Set at least one free provider key:

| Provider | Environment Variable | Models |
|----------|---------------------|--------|
| Groq | `GROQ_API_KEY` | LLaMA 3.3 70B |
| Cerebras | `CEREBRAS_API_KEY` | LLaMA 3.3 70B |
| OpenRouter | `OPENROUTER_API_KEY` | Free-tier models |
| Gemini | `GEMINI_API_KEY` | Gemini Flash |
| Cohere | `COHERE_API_KEY` | Command R+ |
| HuggingFace | `HUGGINGFACE_API_KEY` | Various |

## Architecture

### Components

- **Router** (`router.py`) — Free-model routing via [model-router-ai](https://github.com/FlossWare/model-router-ai). Falls back to `SimpleFreeRouter` if model-router-ai is not installed.
- **Repo** (`repo.py`) — Repository inspection: read/write files, grep, git operations, command execution.
- **Worker** (`worker.py`) — LLM-driven investigation and implementation. Parses structured JSON responses, applies file changes, runs test commands.
- **Arbiter** (`arbiter.py`) — Independent code review with structured accept/reject decisions and actionable feedback.
- **CodingAgent** (`agent.py`) — Orchestrates the worker/arbiter loop with configurable iteration limits.
- **CLI** (`cli.py`) — Command-line interface (`pa` command).

### Composed FlossWare Packages

| Package | Role |
|---------|------|
| [model-router-ai](https://github.com/FlossWare/model-router-ai) | Free-model routing with Thompson Sampling, latency optimization, cost awareness |
| [resilience-ai](https://github.com/FlossWare/resilience-ai) | Circuit breakers, retry logic, fallback chains |
| [structured-output-ai](https://github.com/FlossWare/structured-output-ai) | JSON schema enforcement for LLM outputs |

Optional (install with `pip install ".[all]"`):

| Package | Role |
|---------|------|
| [consensus-ai](https://github.com/FlossWare/consensus-ai) | Multi-model voting for high-confidence decisions |
| [evaluation-ai](https://github.com/FlossWare/evaluation-ai) | Automated quality scoring |
| [observability-ai](https://github.com/FlossWare/observability-ai) | Metrics, tracing, logging |

### Agent Integration

personal-agent is agent-neutral — it works as a library from any coding agent:

- **Claude Code**: See `CLAUDE.md`
- **OpenCode / Codex**: See `AGENTS.md`
- **Cursor**: Import and call from `.cursor/rules`
- **Crush**: Use as a Python library in agent scripts

## Safety

- **Dangerous command blocking**: `rm -rf /`, `mkfs`, fork bombs, etc. are blocked
- **Command timeouts**: All subprocess calls have configurable timeouts (default 120s)
- **No network egress beyond LLM calls**: Worker/arbiter only call the router
- **Git isolation**: Changes are tracked via `git diff`, uncommitted until explicitly requested

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## License

MIT
