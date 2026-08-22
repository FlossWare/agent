"""Free-model router factory.

Creates a model-router-ai stack configured for free models only.
Uses PolicyGuard + CostAware to enforce the free-model policy.
Falls back to a simple direct-call adapter if model-router-ai
is not installed or no API keys are available.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from dataclasses import dataclass, field as dc_field
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

PROVIDER_CONFIGS = [
    {
        "name": "cohere",
        "env": "COHERE_API_KEY",
        "url": "https://api.cohere.com/v2/chat",
        "model": "command-a-03-2025",
        "is_cohere": True,
    },
    {
        "name": "groq",
        "env": "GROQ_API_KEY",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "model": "qwen/qwen3.6-27b",
    },
    {
        "name": "openrouter",
        "env": "OPENROUTER_API_KEY",
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "model": "google/gemma-4-31b-it:free",
    },
    {
        "name": "cerebras",
        "env": "CEREBRAS_API_KEY",
        "url": "https://api.cerebras.ai/v1/chat/completions",
        "model": "llama-3.3-70b",
    },
]


def create_free_router(
    *,
    max_monthly: float = 0.0,
    extra_providers: dict[str, str] | None = None,
) -> Any:
    """Create a model router that only uses free models.

    Discovers API keys from environment variables and configures
    model-router-ai with free-only policy.

    If model-router-ai is not available, returns a SimpleFreeRouter
    that calls providers directly with automatic fallback.
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


@dataclass
class _Response:
    content: str = ""
    model: str = ""
    provider: str = ""
    usage: dict = dc_field(default_factory=dict)
    latency_ms: float = 0.0
    cost_usd: float = 0.0


class SimpleFreeRouter:
    """Minimal fallback router when model-router-ai is not installed.

    Tries multiple providers in order, falling back on API errors.
    Supports both OpenAI-compatible and Cohere APIs.
    """

    def __init__(self, providers: list[dict]) -> None:
        self._providers = providers

    async def initialize(self) -> None:
        pass

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> _Response:
        normalized = [
            {"role": m["role"], "content": m["content"]}
            if isinstance(m, dict)
            else {"role": m.role, "content": m.content}
            for m in messages
        ]

        errors = []
        for provider in self._providers:
            try:
                return self._call_provider(
                    provider, normalized,
                    model=model, temperature=temperature, max_tokens=max_tokens,
                )
            except Exception as e:
                logger.warning("Provider %s failed: %s", provider["name"], e)
                errors.append((provider["name"], str(e)))

        raise RuntimeError(
            "All providers failed:\n"
            + "\n".join(f"  {name}: {err}" for name, err in errors)
        )

    def _call_provider(
        self,
        provider: dict,
        messages: list[dict],
        *,
        model: str | None,
        temperature: float,
        max_tokens: int | None,
    ) -> _Response:
        body: dict[str, Any] = {
            "model": model or provider["model"],
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            body["max_tokens"] = max_tokens

        data = json.dumps(body).encode()
        req = urllib.request.Request(
            provider["url"],
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {provider['key']}",
            },
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())

        if provider.get("is_cohere"):
            content = result.get("message", {}).get("content", [{}])
            if isinstance(content, list) and content:
                content = content[0].get("text", "")
            elif isinstance(content, str):
                pass
            else:
                content = str(content)
        else:
            content = result["choices"][0]["message"]["content"]

        return _Response(
            content=content,
            model=result.get("model", provider["model"]),
            provider=provider["name"],
            usage=result.get("usage", {}),
        )

    async def list_models(self) -> list:
        return []


def _create_simple_router() -> SimpleFreeRouter:
    available = []
    for cfg in PROVIDER_CONFIGS:
        key = os.environ.get(cfg["env"], "")
        if key:
            available.append({**cfg, "key": key})

    if not available:
        raise RuntimeError(
            "No API keys found. Set at least one of: "
            + ", ".join(c["env"] for c in FREE_PROVIDERS.values())
        )

    logger.info(
        "SimpleFreeRouter with %d providers: %s",
        len(available),
        ", ".join(p["name"] for p in available),
    )
    return SimpleFreeRouter(available)
