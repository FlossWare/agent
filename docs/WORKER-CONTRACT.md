# Canonical Worker Contract

Phase 1 establishes one provider-neutral worker boundary for `agent-ai`.

## Work

`Work` is the request crossing the worker boundary:

- `description`: human-readable objective
- `required_capabilities`: capabilities required for execution
- `context`: structured, provider-neutral context

`Task` extends `Work` for coding workflows with repository path, selected files,
commands, and iteration policy. Those fields are coding concerns, not part of
the generic worker protocol.

## Worker

`CapableWorker` is the canonical protocol:

```python
class CapableWorker(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def capabilities(self) -> frozenset[str]: ...

    async def execute(self, work: Work) -> WorkerResult: ...
```

A worker can be deterministic code, a CLI, MCP capability, another agent, a
local model, a hosted model, a test runner, or a composite worker.

## WorkerResult

`WorkerResult` is the canonical evidence envelope. Generic consumers use:

- `worker`
- `success`
- `evidence`
- `confidence`
- `capabilities`
- `metadata`

Coding workers may additionally populate `plan`, `findings`, `changes`,
`test_results`, `model_used`, and `raw_response`. These are compatibility and
structured-evidence fields, not requirements for every worker.

## Provider boundary

The worker contract does not select providers, accounts, models, credentials,
or pricing. Those belong to routing and policy. `model-router-ai` supplies the
provider/account/model selection behind the worker implementation.

The worker result may record routing provenance in `metadata`, but workers must
not require a particular provider implementation.

## Arbitration boundary

`CapabilityArbiter` consumes `CapableWorker` and canonical `WorkerResult`
objects. More sophisticated arbitration can be supplied by `consensus-ai`.
The worker protocol does not depend on a particular arbitration strategy.

## Verification boundary

Tests and deterministic hard gates remain independent evidence. Verification
can consume worker artifacts and test results through `evaluation-ai` without
changing the worker contract.

## Compatibility

The existing coding `Worker` remains intact during this migration. The
`CodingWorkerAdapter` exposes it through `CapableWorker`, allowing Phase 1 to
establish the new boundary without a risky all-at-once rewrite.

The next step is to put `model-router-ai` behind this boundary and then replace
coding-specific assumptions in orchestration paths incrementally.
