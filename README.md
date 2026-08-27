# coding-agent-ai

FlossWare coding-agent execution/orchestration stack built around a provider-neutral **worker / arbiter** architecture.

## Core model

A **worker is any capable unit of work**. It is not synonymous with an LLM. A worker may be deterministic code, a CLI, MCP capability, another agent, a local model, a hosted model, a test runner, or a composite worker.

```text
Work
  -> capability matching
  -> Workers
       -> deterministic tool
       -> CLI
       -> MCP capability
       -> agent
       -> model
       -> composite worker
  -> Arbiter
       -> collect evidence
       -> detect disagreement
       -> synthesize
  -> Result
```

The arbiter is the synthesis boundary. Model-based consensus is one possible synthesis implementation, not a prerequisite for the architecture.

## Model fabric

Model execution uses four independent concepts:

```text
Provider + Account + Model = Worker
                              |
                         Worker Pool
                              |
                           Arbiter
```

- **Provider** is an API/runtime transport.
- **Account** is a credential identity within a provider.
- **Model** is independent of provider and account.
- **Worker** is one concrete provider/account/model route.

This means one exhausted OpenRouter account does not disable another OpenRouter
account, a local model, or another provider. Workers record structured failure
states and honor provider quota reset times.

Explicit workers can be configured with `FLOSSWARE_WORKERS_CONFIG`:

```json
[
  {
    "id": "openrouter/flossware/qwen",
    "provider": "openrouter",
    "account": "flossware",
    "model": "qwen/qwen3-coder",
    "endpoint": "https://openrouter.ai/api/v1/chat/completions",
    "api_key_env": "OPENROUTER_FLOSSWARE_KEY",
    "capabilities": ["chat", "code"]
  },
  {
    "id": "openrouter/ncrr/qwen",
    "provider": "openrouter",
    "account": "ncrr",
    "model": "qwen/qwen3-coder",
    "endpoint": "https://openrouter.ai/api/v1/chat/completions",
    "api_key_env": "OPENROUTER_NCRR_KEY",
    "capabilities": ["chat", "code"]
  },
  {
    "id": "local/qwen",
    "provider": "local",
    "account": "local",
    "model": "qwen3-coder",
    "endpoint": "http://127.0.0.1:8000/v1/chat/completions",
    "api_key_env": "LOCAL_API_KEY",
    "capabilities": ["chat", "code"]
  }
]
```

Credentials are referenced by environment variable and never stored in the
configuration itself. An absent worker configuration produces zero explicit
workers. Existing provider-specific environment variables remain supported as
a compatibility path.

See `docs/adr/0001-provider-account-model-worker-fabric.md` for the architectural decision.

## Coding-agent workflow

The repository also provides a concrete software-engineering worker/arbiter loop:

```text
Task -> isolated worktree -> Worker -> Tests -> Hard gates -> Arbiter -> Accept/Reject -> Apply
```

1. Each run can execute in a disposable git worktree.
2. A coding worker investigates, plans, changes files, and runs tests.
3. Deterministic hard gates can reject failures regardless of model output.
4. An independent arbiter reviews the proposed result.
5. Rejection feeds actionable feedback back to the worker for another iteration.
6. Accepted changes can be applied to the primary tree.

## Provider and pricing neutrality

Provider, model, vendor, hosting topology, authentication mechanism, and pricing are **routing and policy inputs**, not architectural defaults. The runtime does not require or prefer a particular provider or pricing tier.

See `personal_agent/capability.py` for the generic capability-worker contract and `personal_agent/arbiter.py` for the coding-review arbiter.

## Install on Fedora

For the current dogfood milestone, use `FlossWare/coding-agent-setup` as the installation entry point. Fedora is the Tier-1 supported installation target.

```bash
git clone https://github.com/FlossWare/coding-agent-setup.git
cd coding-agent-setup
./scripts/install.sh
```

## Quick start

After installation and explicit authentication/configuration:

```bash
cd /path/to/your/git/repository
source ~/.flossware/venv/bin/activate
pa --investigate "What are the main components?" --repo .
pa "Fix the failing test in test_auth.py" --repo . --commands pytest --max-iter 3
```

Do not use `--commit` on the first dogfood run. Review the generated diff and verification results first.

## Generic capability API

```python
import asyncio
from personal_agent import CapabilityArbiter, FunctionWorker, Work

async def main():
    workers = [
        FunctionWorker("static-check", {"inspect"}, lambda work: "static evidence"),
        FunctionWorker("tests", {"inspect", "verify"}, lambda work: "tests evidence"),
    ]
    result = await CapabilityArbiter(workers).execute(
        Work("inspect repository", frozenset({"inspect"}))
    )
    print(result.conclusion)

asyncio.run(main())
```

This API deliberately has no provider-specific dependency. A model-backed worker can be added without changing the work or arbiter contracts.

## Credentials

Credentials belong to the authentication boundary and must not be embedded in source, generated configuration, images, or Git history. Existing authenticated CLI/session capabilities SHOULD be reused where supported rather than requiring duplicate credentials.

## Safety

- command policy and filesystem confinement
- credential isolation and secret redaction
- deterministic verification gates
- disposable worktrees
- independent arbitration

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
```

## License

MIT
