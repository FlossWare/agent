"""Provider/account/model/worker router.

The public ``chat`` API remains compatible with the coding agent while routing
through independent workers. Providers and accounts are deliberately separate
so one exhausted identity does not disable its siblings.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field as dc_field
from typing import Any

from personal_agent.model_fabric import Account, Arbiter as WorkerArbiter, Model, ModelWorker, Provider, WorkerPool, load_worker_config, workers_from_config


@dataclass
class _Response:
    content: str = ""
    model: str = ""
    provider: str = ""
    account: str = ""
    usage: dict = dc_field(default_factory=dict)
    latency_ms: float = 0.0
    cost_usd: float = 0.0


FREE_PROVIDERS = {
    "groq": {"env": "GROQ_API_KEY", "name": "groq", "model": "qwen/qwen3.6-27b"},
    "cerebras": {"env": "CEREBRAS_API_KEY", "name": "cerebras", "model": "llama-3.3-70b"},
    "openrouter": {"env": "OPENROUTER_API_KEY", "name": "openrouter", "model": "openai/gpt-4o-mini"},
    "gemini": {"env": "GEMINI_API_KEY", "name": "gemini", "model": "gemini-2.5-flash"},
    "cohere": {"env": "COHERE_API_KEY", "name": "cohere", "model": "command-a-03-2025"},
    "huggingface": {"env": "HUGGINGFACE_API_KEY", "name": "huggingface", "model": ""},
}


def _endpoint(name: str) -> str:
    return {
        "groq": "https://api.groq.com/openai/v1/chat/completions",
        "cerebras": "https://api.cerebras.ai/v1/chat/completions",
        "openrouter": "https://openrouter.ai/api/v1/chat/completions",
        "cohere": "https://api.cohere.com/v2/chat",
        "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "huggingface": "https://router.huggingface.co/v1/chat/completions",
    }[name]


PROVIDER_CONFIGS = []
for _name, _cfg in FREE_PROVIDERS.items():
    _entry = {**_cfg, "url": _endpoint(_name)}
    if _name == "cohere":
        _entry["is_cohere"] = True
    PROVIDER_CONFIGS.append(_entry)


class FabricRouter:
    """OpenAI-compatible facade over the provider-neutral worker fabric."""

    def __init__(self, pool: WorkerPool) -> None:
        self.pool = pool
        self.arbiter = WorkerArbiter(pool)
        self._providers = pool.workers

    async def initialize(self) -> None:
        return None

    async def chat(self, messages: list[dict[str, str]], *, model: str | None = None,
                   temperature: float = 0.7, max_tokens: int | None = None, **kwargs: Any) -> _Response:
        selected_model = None if model in (None, "flossware") else model
        try:
            result = await self.arbiter.execute(messages, model=selected_model,
                                                temperature=temperature, max_tokens=max_tokens, **kwargs)
        except RuntimeError as exc:
            raise RuntimeError(str(exc).replace("No worker succeeded", "All providers failed")) from exc
        return _Response(content=result.content, model=result.model, provider=result.provider,
                         account=result.account, usage=result.usage, latency_ms=result.latency_ms,
                         cost_usd=result.cost_usd)

    async def list_models(self) -> list[dict[str, str]]:
        seen: set[str] = set()
        result = []
        for worker in self.pool.workers:
            if worker.model.id not in seen:
                seen.add(worker.model.id)
                result.append({"id": worker.model.id, "provider": worker.provider.id})
        return result


class SimpleFreeRouter(FabricRouter):
    """Backward-compatible constructor accepting old provider dictionaries."""

    def __init__(self, providers: list[dict[str, Any]]) -> None:
        workers: list[ModelWorker] = []
        for item in providers:
            provider = Provider(item["name"], item["url"])
            account = Account(item["name"] + "/default", item["name"], "__unused__", item.get("key", ""))
            model = Model(item["model"], frozenset({"chat"}))
            workers.append(ModelWorker(item["name"], provider, account, model))
        super().__init__(WorkerPool(workers))


SimpleRouter = SimpleFreeRouter


def create_router(*, max_monthly: float | None = None, extra_providers: dict[str, str] | None = None) -> FabricRouter:
    """Create a router from explicit worker config or legacy API keys."""
    config = load_worker_config()
    if config:
        return FabricRouter(workers_from_config(config))
    return create_free_router(extra_providers=extra_providers)


def create_free_router(*, extra_providers: dict[str, str] | None = None) -> FabricRouter:
    config = _legacy_worker_config(extra_providers)
    if not config:
        raise RuntimeError("No API keys found. Configure at least one supported provider credential.")
    return FabricRouter(workers_from_config(config))


def _legacy_worker_config(extra_providers: dict[str, str] | None = None) -> list[dict[str, Any]]:
    config: list[dict[str, Any]] = []
    for name, cfg in FREE_PROVIDERS.items():
        if os.environ.get(cfg["env"], "") and cfg["model"]:
            config.append({"id": f"{name}/default/{cfg['model']}", "provider": name,
                           "account": "default", "model": cfg["model"], "endpoint": _endpoint(name),
                           "api_key_env": cfg["env"], "capabilities": ["chat"]})
    if extra_providers:
        for name, env_var in extra_providers.items():
            if os.environ.get(env_var, ""):
                config.append({"id": f"{name}/default/{name}", "provider": name, "account": "default",
                               "model": name, "endpoint": _endpoint(name) if name in FREE_PROVIDERS else name,
                               "api_key_env": env_var, "capabilities": ["chat"]})
    return config


def _create_simple_router() -> FabricRouter:
    return create_free_router()


def _create_model_router_ai(*args: Any, **kwargs: Any) -> Any:
    raise ImportError("model-router-ai integration is superseded by the worker fabric")
