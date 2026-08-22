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

All `CodingAgent` methods are async. Use within an `async def` or wrap with `asyncio.run()`:

```python
import asyncio
from personal_agent import CodingAgent, Task, Decision

async def main():
    agent = CodingAgent("/path/to/repo")
    result = await agent.run(Task(
        description="Fix the bug in auth.py",
        commands=["pytest tests/"],
        max_iterations=3,
    ))

    if result.decision == Decision.ACCEPT:
        print(result.final_diff)
        print(result.commit_message)

asyncio.run(main())
```

### Handling Rejections

The `TaskResult` includes the full history of worker/arbiter iterations:

```python
result = await agent.run(task)

if result.decision == Decision.REJECT:
    print(f"Rejected after {result.iterations} iterations")
    for d in result.arbiter_decisions:
        print(f"  {d.decision.value}: {d.reason}")
        for f in d.findings:
            print(f"    [{f.severity}] {f.description}")
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

| Provider | Environment Variable | Default Model | Notes |
|----------|---------------------|---------------|-------|
| Cohere | `COHERE_API_KEY` | command-a-03-2025 | Recommended — most reliable |
| Groq | `GROQ_API_KEY` | qwen/qwen3.6-27b | Fast inference |
| OpenRouter | `OPENROUTER_API_KEY` | google/gemma-4-31b-it:free | Free-tier models |
| Cerebras | `CEREBRAS_API_KEY` | llama-3.3-70b | Fast inference |
| Gemini | `GEMINI_API_KEY` | Gemini Flash | Via model-router-ai only |
| HuggingFace | `HUGGINGFACE_API_KEY` | Various | Via model-router-ai only |

Set multiple keys for automatic failover — if one provider errors, the next is tried.

## Architecture

### Components

- **Router** (`router.py`) — Free-model routing. When [model-router-ai](https://github.com/FlossWare/model-router-ai) is installed, uses its full decorator stack (Thompson Sampling, latency optimization, cost awareness). Otherwise, falls back to the built-in `SimpleFreeRouter` which provides basic multi-provider failover without external dependencies.
- **Repo** (`repo.py`) — Repository inspection: read/write files, grep, git operations, command execution.
- **Worker** (`worker.py`) — LLM-driven investigation and implementation. Parses structured JSON responses (with recovery for malformed LLM output), applies file changes, runs test commands. Blocks dangerous commands.
- **Arbiter** (`arbiter.py`) — Independent code review with structured accept/reject decisions and actionable feedback.
- **CodingAgent** (`agent.py`) — Orchestrates the worker/arbiter loop with configurable iteration limits.
- **CLI** (`cli.py`) — Command-line interface (`pa` command).

### Two Routing Modes

**With model-router-ai installed** (recommended): Uses the full decorator stack — PolicyGuard, CostAware, LatencyOptimizer, ThompsonSamplingSelector — for intelligent model selection with Bayesian explore/exploit.

**Without model-router-ai** (zero-dependency fallback): The built-in `SimpleFreeRouter` tries each configured provider in order, falling back automatically on API errors. Supports both OpenAI-compatible APIs and Cohere's v2 chat API natively.

### Malformed JSON Recovery

LLMs sometimes return invalid JSON (triple-quoted strings, trailing commas). The worker includes a `_fix_malformed_json` method that handles these common mistakes before falling back to a plain-text response.

### Composed FlossWare Packages

| Package | Role |
|---------|------|
| [model-router-ai](https://github.com/FlossWare/model-router-ai) | Free-model routing with Thompson Sampling, latency optimization, cost awareness, injectable protocols |
| [resilience-ai](https://github.com/FlossWare/resilience-ai) | Circuit breakers, retry logic, fallback chains |
| [structured-output-ai](https://github.com/FlossWare/structured-output-ai) | JSON schema enforcement for LLM outputs |

Optional (install with `pip install ".[all]"`):

| Package | Role |
|---------|------|
| [consensus-ai](https://github.com/FlossWare/consensus-ai) | Multi-model voting for high-confidence decisions |
| [evaluation-ai](https://github.com/FlossWare/evaluation-ai) | Automated quality scoring |
| [observability-ai](https://github.com/FlossWare/observability-ai) | Metrics, tracing, logging |

### Public API

All primary types are exported from the top-level package:

```python
from personal_agent import (
    CodingAgent,        # Main orchestration loop
    Worker,             # LLM-driven code worker
    Arbiter,            # Independent code reviewer
    Task,               # Task description
    TaskResult,         # Full result with decisions and diffs
    WorkerResult,       # Worker output (plan, findings, changes)
    ArbiterDecision,    # Structured accept/reject
    Decision,           # ACCEPT / REJECT enum
    FileChange,         # Single file modification
    CommandResult,      # Shell command result
    create_free_router, # Router factory
)
```

### Agent Integration

personal-agent is agent-neutral — it works as a library from any coding agent:

- **Claude Code**: See `CLAUDE.md`
- **OpenCode / Codex**: See `AGENTS.md`
- **Cursor**: Import and call from `.cursor/rules`
- **Crush**: Use as a Python library in agent scripts

## Safety

- **Dangerous command blocking**: `rm -rf /`, `mkfs`, `sudo`, pipe-to-shell, fork bombs, and 20+ other patterns are blocked
- **Command timeouts**: All subprocess calls have configurable timeouts (default 120s)
- **No network egress beyond LLM calls**: Worker/arbiter only call the router
- **Git isolation**: Changes are tracked via `git diff`, uncommitted until explicitly requested

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v    # 65 tests
```

## License

MIT
