"""Free-model router factory.

Creates a model-router-ai stack configured for free models only.
Uses PolicyGuard + CostAware to enforce the free-model policy.
Falls back to a simple direct-call adapter if model-router-ai
is not installed or no API keys are available.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

FREE_PROVIDERS = {
    "groq": {
        "env": "GROQ_API_KEY",
        "name": "groq",
    },
    "cerebras": {
        "env": "CEREBRAS_API_KEY",
        "name": "cerebras",
    },
    "openrouter": {
        "env": "OPENROUTER_API_KEY",
        "name": "openrouter",
    },
    "gemini": {
        "env": "GEMINI_API_KEY",
        "provider": "gemini",
    },
    "cohere": {
        "env": "COHERE_API_KEY",
        "provider": "cohere",
    },
    "huggingface": {
        "env": "HUGGINGFACE_API_KEY",
        "name": "huggingface",
    },
}


def create_free_router(
    *,
    max_monthly: float = 0.0,
    extra_providers: dict[str, str] | None = None,
) -> Any:
    """Create a model router that only uses free models.

    Discovers API keys from environment variables and configures
    model-router-ai with free-only policy.

    If model-router-ai is not available, returns a SimpleFreeRouter
    that calls providers directly.

    Parameters
    ----------
    max_monthly:
        Budget cap (0 = unlimited for free models).
    extra_providers:
        Additional provider_name -> env_var_name mappings.
    """
    try:
        return _create_model_router_ai(max_monthly, extra_providers)
    except ImportError:
        logger.info("model-router-ai not installed, using SimpleFreeRouter")
        return _create_simple_router()


def _create_model_router_ai(
    max_monthly: float,
    extra_providers: dict[str, str] | None,
) -> Any:
    from model_router_ai import (
        CostAware,
        LatencyOptimizer,
        OpenAICompatProvider,
        GeminiProvider,
        CohereProvider,
        PolicyGuard,
        ProviderRouter,
        ThompsonSamplingSelector,
    )

    base = ProviderRouter()
    added = 0

    for name, cfg in FREE_PROVIDERS.items():
        key = os.environ.get(cfg["env"], "")
        if not key:
            continue

        if name == "gemini":
            base.add_provider(GeminiProvider(), api_key=key)
            added += 1
        elif name == "cohere":
            base.add_provider(CohereProvider(), api_key=key)
            added += 1
        else:
            base.add_provider(
                OpenAICompatProvider(cfg["name"]),
                api_key=key,
            )
            added += 1

    if extra_providers:
        for pname, env_var in extra_providers.items():
            key = os.environ.get(env_var, "")
            if key:
                base.add_provider(OpenAICompatProvider(pname), api_key=key)
                added += 1

    if added == 0:
        raise RuntimeError(
            "No API keys found. Set at least one of: "
            + ", ".join(c["env"] for c in FREE_PROVIDERS.values())
        )

    router = PolicyGuard(
        CostAware(
            LatencyOptimizer(
                ThompsonSamplingSelector(base),
            ),
            prefer_free=True,
        ),
    )

    logger.info("Created model-router-ai stack with %d free providers", added)
    return router


class SimpleFreeRouter:
    """Minimal fallback router when model-router-ai is not installed.

    Calls a single provider's OpenAI-compatible API directly.
    """

    def __init__(self, provider: str, api_key: str, base_url: str, model: str) -> None:
        self._provider = provider
        self._api_key = api_key
        self._base_url = base_url
        self._model = model

    async def initialize(self) -> None:
        pass

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> Any:
        import json
        import urllib.request

        url = f"{self._base_url}/chat/completions"
        body = {
            "model": model or self._model,
            "messages": [{"role": m["role"], "content": m["content"]}
                         if isinstance(m, dict) else {"role": m.role, "content": m.content}
                         for m in messages],
            "temperature": temperature,
        }
        if max_tokens:
            body["max_tokens"] = max_tokens

        data = json.dumps(body).encode()
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())

        from dataclasses import dataclass, field as dc_field

        @dataclass
        class _Response:
            content: str = ""
            model: str = ""
            provider: str = ""
            usage: dict = dc_field(default_factory=dict)
            latency_ms: float = 0.0
            cost_usd: float = 0.0

        return _Response(
            content=result["choices"][0]["message"]["content"],
            model=result.get("model", self._model),
            provider=self._provider,
            usage=result.get("usage", {}),
        )

    async def list_models(self) -> list:
        return []


def _create_simple_router() -> SimpleFreeRouter:
    providers = [
        ("groq", "GROQ_API_KEY", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
        ("cerebras", "CEREBRAS_API_KEY", "https://api.cerebras.ai/v1", "llama-3.3-70b"),
        ("openrouter", "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1", "meta-llama/llama-3.3-70b-instruct:free"),
    ]
    for name, env, url, model in providers:
        key = os.environ.get(env, "")
        if key:
            return SimpleFreeRouter(name, key, url, model)

    raise RuntimeError(
        "No API keys found. Set at least one of: "
        + ", ".join(c["env"] for c in FREE_PROVIDERS.values())
    )
