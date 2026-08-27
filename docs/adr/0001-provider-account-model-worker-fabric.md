# ADR 0001: Provider, Account, Model, and Worker Fabric

- Status: Accepted
- Date: 2026-08-27

## Context

FlossWare must be able to use local models, hosted APIs, multiple accounts for
the same provider, and multiple models without making the coding agent depend
on one vendor. Provider-wide failure is also too coarse: a provider may have
several independent identities with different quotas and credentials.

A recent OpenRouter `free-models-per-day` HTTP 429 demonstrated the failure
mode. Exhausting one identity must not cause other identities or providers to
be abandoned, and the router must not repeatedly retry an exhausted identity
until its reset time.

## Decision

Use a provider-neutral model fabric with four independent concepts:

1. **Provider**: transport/API endpoint and protocol kind.
2. **Account**: credential identity belonging to a provider. Credentials are
   referenced by environment variable and are never stored in configuration.
3. **Model**: model identity and capabilities, independent of account/provider.
4. **Worker**: a concrete executable route consisting of provider + account +
   model + worker configuration.

Workers are collected into a `WorkerPool`. An `Arbiter` selects eligible
workers and fails over between them. The public coding-agent router remains an
OpenAI-compatible `chat()` facade.

Worker execution returns structured statuses including `SUCCESS`,
`RATE_LIMITED`, `QUOTA_EXHAUSTED`, `AUTH_FAILED`, `MODEL_UNAVAILABLE`,
`TIMEOUT`, `NETWORK_ERROR`, `INVALID_REQUEST`, and `FAILED`.

A 429 with a known quota/reset time marks only that worker unavailable until
the reset. Other workers remain eligible.

## Configuration

Explicit workers are configured through `FLOSSWARE_WORKERS_CONFIG` as JSON.
Each entry references an API-key environment variable:

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

No worker is enabled unless it is explicitly configured and its referenced
credential exists. Existing single-provider environment variables remain
supported for compatibility.

## Consequences

### Positive

- Multiple providers, accounts, and models can coexist.
- Quota is isolated per worker/account.
- The coding agent is not coupled to OpenRouter.
- Local and remote OpenAI-compatible runtimes share the same execution path.
- Future selection strategies can replace the basic arbiter without changing
  provider adapters or workers.
- Thompson Sampling, consensus, adversarial review, and genetic optimization
  can be layered above this substrate later.

### Negative

- There are more concepts than a single-provider router.
- Native non-OpenAI-compatible APIs need dedicated adapters.
- Persistent quota/health state is not yet required by the first implementation.

## Rejected alternatives

### Provider-only routing

Rejected because it cannot isolate accounts or credentials within one
provider.

### Model-only routing

Rejected because the same model can be available through multiple providers,
accounts, and hosting topologies.

### OpenRouter-specific fallback logic

Rejected because it creates vendor coupling and does not solve local models or
other APIs.

### Thompson Sampling as the initial router

Rejected for the initial implementation. Statistical optimization belongs in
the selection policy layer after the deterministic worker substrate is stable.
