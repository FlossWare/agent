# coding-agent-ai

FlossWare coding-agent execution/orchestration stack that composes FlossWare capabilities into a worker/arbiter loop for real software-engineering workflows.

**Provider- and pricing-neutral.** Model selection and routing are delegated to FlossWare's model-routing layer. The runtime does not require, prefer, or assume a particular provider, vendor, hosting topology, or pricing tier. Selection is determined by capability, policy, availability, authentication, cost, and other workload constraints as applicable.

## How It Works

```text
Task → isolated worktree → Worker → Tests → Hard gates → Arbiter → Accept/Reject → Apply → Commit
```

1. **Worktree** — each run executes in a disposable git worktree so the primary checkout is untouched until acceptance.
2. **Worker** receives a task, inspects the repository, formulates a plan, makes changes, and runs tests.
3. **Hard gates** force REJECT on test failures or security-policy violations. The model cannot override them.
4. **Arbiter** independently reviews changes with structured accept/reject decisions.
5. If **rejected**, the worker receives actionable feedback and retries up to the configured iteration limit.
6. If **accepted**, the worktree diff is applied to the primary tree and is ready for review/commit/PR.

## Install on Fedora

For the current dogfood milestone, use `FlossWare/coding-agent-setup` as the installation entry point. Fedora is the Tier-1 supported installation target.

```bash
git clone https://github.com/FlossWare/coding-agent-setup.git
cd coding-agent-setup
./scripts/install.sh
```

The installer creates an isolated environment under `~/.flossware/venv`, installs `coding-agent-ai` and its selected FlossWare capabilities, validates the runtime, and installs `~/.local/bin/flossware-setup`.

See [coding-agent-setup Fedora guide](https://github.com/FlossWare/coding-agent-setup/blob/main/docs/platforms/fedora.md).

## Quick Start

```bash
cd /path/to/your/git/repository
~/.local/bin/flossware-setup

# After authentication/configuration:
source ~/.flossware/venv/bin/activate
pa --investigate "What are the main components?" --repo .
pa "Fix the failing test in test_auth.py" --repo . --commands pytest --max-iter 3
```

Do not use `--commit` on the first dogfood run. Review the generated diff and test results before enabling automatic commits.

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

asyncio.run(main())
```

> **Compatibility note:** the distribution/repository is `coding-agent-ai`; the Python import package remains `personal_agent` for API compatibility. A future major release may provide a `coding_agent_ai` import with a compatibility shim.

## Provider Credentials

The runtime consumes provider/router credentials through the configured authentication boundary. Supported environment variables currently include:

| Provider | Environment Variable |
|----------|---------------------|
| Cohere | `COHERE_API_KEY` |
| Groq | `GROQ_API_KEY` |
| OpenRouter | `OPENROUTER_API_KEY` |
| Cerebras | `CEREBRAS_API_KEY` |
| Gemini | `GEMINI_API_KEY` |
| HuggingFace | `HUGGINGFACE_API_KEY` |

These are integration examples, not a closed provider list or architectural preference. Credentials must remain outside generated source/configuration artifacts. Where a provider exposes an existing authenticated CLI/session, setup SHOULD reuse that capability rather than requiring duplicate credentials.

## Architecture

```text
request
  -> policy / model router
  -> provider-neutral contract
  -> cross-cutting decorators
  -> provider adapter
  -> model/runtime
```

Decorators provide cross-cutting behavior such as resilience, security, observability, evaluation, structured-output validation, and token/cost accounting. They must not encode provider or pricing preferences.

## Safety

See [docs/SECURITY.md](docs/SECURITY.md).

- **Command policy** — allowlist/denylist, argv execution, network as explicit capability
- **Filesystem confinement** — paths must resolve under workspace root
- **Credential isolation** — provider/repo/cloud/registry/SSH secrets stripped from worker env
- **Secret redaction** — tokens redacted from logs, prompts, and feedback (`SecretRedactor`)
- **Hard verification gates** — tests/policy/syntax failures force REJECT; the model cannot override
- **Disposable worktrees** — primary tree unchanged until accepted diff is applied

## Development

```bash
source ~/.flossware/venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

## License

MIT
