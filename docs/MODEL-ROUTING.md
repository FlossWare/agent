# Model routing boundary

`agent-ai` does not own provider, account, model, credential, quota, or routing policy. Those concerns belong to `model-router-ai`.

## Flow

```text
Work
  -> CapableWorker
       -> model-router-ai ModelRouter
            -> provider/account/model worker
            -> provider call
       <- ChatResponse
  <- WorkerResult
```

The coding worker continues to consume the small `chat()` surface. `personal_agent.router.create_router()` is the compatibility boundary that constructs a `model-router-ai.ProviderRouter` from configured accounts.

## Accounts

`model-router-ai` discovers configured accounts from the canonical FlossWare AI state root and environment-backed credentials. Each configured account is registered with its account ID, so health, quota, and model selection remain associated with a concrete provider/account/model endpoint.

Credential values are read only at the routing boundary and are never placed in `Work` or the generic `WorkerResult` contract.

## Free-only routing

Callers can request `create_router(free_only=True)`. The adapter only registers providers marked `free_capable` by `model-router-ai`; OpenRouter is additionally configured to discover only free-priced models.

This is routing policy, not a worker concern.

## Budget

`create_router(max_monthly=...)` wraps the canonical router with `model-router-ai.BudgetGuard`. The previous `CostAware(max_monthly=...)` usage was incorrect because `CostAware` controls per-call cost preference, while `BudgetGuard` enforces the monthly spending ceiling.

## Provider-neutral worker results

The worker contract does not expose provider-specific classes. Existing coding compatibility fields such as `model_used` remain transitional. Generic consumers should use `WorkerResult.evidence`, `confidence`, `capabilities`, and `metadata` rather than provider-specific fields.

The model router's response provides provider/model metadata without exposing credentials.

## Canonical state root

`model-router-ai` follows `FLOSSWARE_AI_HOME` when set, otherwise `~/.FlossWare/ai`, matching `agent-setup`. The account configuration is read from `config/accounts.toml` beneath that root unless `FLOSSWARE_ACCOUNTS_FILE` overrides it.

Repositories remain responsible for source code. Persistent AI account/model/profile state belongs under the canonical AI state root.
