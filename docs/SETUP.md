# agent-ai setup and integration

`agent-ai` is the execution/orchestration layer. It is not the installation or profile-management tool.

## Install the control plane

Use `FlossWare/agent-setup` for installation, configuration profiles, provider/model discovery, diagnostics, and external-agent setup.

Canonical bootstrap:

```bash
curl -fsSL https://raw.githubusercontent.com/FlossWare/agent-setup/main/install.sh | bash
```

Then use the shared CLI/TUI from `agent-setup` to configure the environment and profiles.

## Install agent-ai for development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
```

## Runtime boundary

The runtime accepts work and coordinates workers and arbitration. A worker is any capable unit of work, including deterministic code, a CLI, MCP capability, another agent, a local model, a hosted model, a test runner, or a composite worker.

The architecture is intentionally provider-neutral:

```text
Task
  -> agent-ai
      -> workers
          -> tools / CLI / MCP / agents / models
      -> deterministic verification
      -> arbiter
  -> accepted result
```

Provider, account, model, authentication, and pricing choices are routing and policy concerns. Use `model-router-ai` for provider/account/model routing rather than embedding provider-specific selection in agent-ai.

Use `consensus-ai` where model-based consensus or reusable arbitration strategies are appropriate. Consensus is an implementation option, not a requirement of the worker/arbiter contract.

## Engineering workflow

A typical software-engineering run is:

```text
Issue/task
  -> isolated worktree
  -> worker investigation/change
  -> tests and hard gates
  -> independent arbiter review
  -> retry on rejection
  -> apply accepted change
  -> commit / PR
```

Do not treat model output as authoritative. Deterministic tests and hard gates remain authoritative, and the arbiter evaluates evidence rather than blindly accepting a worker's conclusion.

## Crush integration

`agent-setup` provisions and configures Crush. `crush-demo` is the integration/acceptance harness. `agent-ai` supplies the execution/orchestration runtime.

Keep these responsibilities separate. Do not duplicate setup, provider routing, or consensus logic inside agent-ai.

## Related repositories

- `FlossWare/agent-setup`: installation, profiles, discovery, diagnostics, and external-agent setup.
- `FlossWare/model-router-ai`: provider/account/model routing.
- `FlossWare/consensus-ai`: reusable consensus/arbitration strategies.
- `FlossWare/crush-demo`: integration and acceptance harness.

Existing capability libraries should be reused rather than duplicated.
