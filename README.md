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

## Usage examples

### CLI

```bash
# Investigation only (no accept/apply loop)
pa --investigate "What are the main components?" --repo .

# Coding loop with a deterministic test gate
pa "Fix the failing test in test_auth.py" --repo . --commands pytest --max-iter 3

# Verbose logging and machine-readable output
pa -v "Summarize the security model" --repo . --json
```

Do not use `--commit` on the first dogfood run. Review the generated diff and verification results first.

### Python API — capability workers (provider-neutral)

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

This API has no provider-specific dependency. A model-backed worker can be added without changing the work or arbiter contracts.

### Python API — coding agent loop

```python
import asyncio
from personal_agent import CodingAgent
from personal_agent.types import Task

async def main():
    repo = "/path/to/git/repository"
    agent = CodingAgent(repo, max_iterations=3)
    task = Task(
        description="Fix the failing test in test_auth.py",
        repo_path=repo,
        commands=["pytest"],
        max_iterations=3,
    )
    result = await agent.run(task)
    print(result.decision, result.iterations)
    # Review result.final_diff and result.arbiter_decisions before any commit.

asyncio.run(main())
```

Configure provider credentials in the parent process via `coding-agent-setup`
(or OS secret stores). Workers remain credential-free — see
[docs/SECURITY.md](docs/SECURITY.md). Integration coverage lives under `tests/`
(`test_agent.py`, `test_security.py`, `test_verification.py`).

## Credentials

Credentials belong to the authentication boundary and must not be embedded in
source, generated configuration, images, or Git history. Existing authenticated
CLI/session capabilities SHOULD be reused where supported rather than requiring
duplicate credentials.

Threat model, credential classes, worktree isolation, and redaction:
**[docs/SECURITY.md](docs/SECURITY.md)**.

## Safety

- command policy and filesystem confinement ([docs/COMMAND-POLICY.md](docs/COMMAND-POLICY.md))
- credential isolation and secret redaction ([docs/SECURITY.md](docs/SECURITY.md))
- deterministic verification gates
- disposable worktrees
- independent arbitration

## Testing

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
```

| Metric | v0.1.0 |
|--------|--------|
| Test functions (`def test_*`) | **172** across `tests/` |
| Coverage percentage | Not published yet; report in CI before v0.2.0 |
| Security / gates focus | `pytest tests/test_security.py tests/test_verification.py -v` |

## Troubleshooting and known limitations

**[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)** covers common errors, debug
mode (`pa -v`), worktree cleanup, router timeouts, and rejection-loop exhaustion.

| Limitation | Notes |
|------------|--------|
| Python **3.11+** | Required by `requires-python` and shared FlossWare typing/runtime choices. |
| Fedora Tier-1 | Primary dogfood path via `coding-agent-setup`; other platforms best-effort. |
| `--max-iter` default **3** | Bounds cost and runaway reject loops; raise when feedback converges. |
| Git `HEAD` dependency pins | Dogfood-only; pin tags/SHAs in v0.2.0+ ([docs/VERSIONING.md](docs/VERSIONING.md)). |
| Worker untrusted vs host | Hard gates can force REJECT regardless of model output. |

Rename migration: [docs/MIGRATION.md](docs/MIGRATION.md).

## License

MIT
