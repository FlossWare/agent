"""Provider-neutral model routing for agent workers.

``model-router-ai`` owns provider, account, model, credential, health, and
selection policy. This module is the agent-ai compatibility boundary: it
constructs that router from the configured accounts while retaining the
small ``chat`` interface expected by the existing coding worker.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from dataclasses import dataclass, field as dc_field
from typing import Any

logger = logging.getLogger(__name__)

# Retained as a compatibility/discovery summary for existing callers. The
# authoritative provider/account definitions live in model-router-ai.
PROVIDERS = {
    "groq": {"env": "GROQ_API_KEY", "name": "groq", "model": "qwen/qwen3.6-27b"},
    "cerebras": {"env": "CEREBRAS_API_KEY", "name": "cerebras", "model": "llama-3.3-70b"},
    "openrouter": {"env": "OPENROUTER_API_KEY", "name": "openrouter", "model": "openai/gpt-4o-mini"},
    "gemini": {"env": "GEMINI_API_KEY", "name": "gemini", "model": "gemini-2.5-flash"},
    "cohere": {"env": "COHERE_API_KEY", "name": "cohere", "model": "command-a-03-2025"},
    "huggingface": {"env": "HUGGINGFACE_API_KEY", "name": "huggingface", "model": ""},
}


def create_router(
    *,
    max_monthly: float | None = None,
    extra_providers: dict[str, str] | None = None,
    free_only: bool = False,
) -> Any:
    """Create the canonical model-router-ai router.

    ``free_only`` restricts provider registration to providers declared free
    capable by model-router-ai and enables OpenRouter's free-model filter.
    ``extra_providers`` is retained for compatibility and adds OpenAI-compatible
    providers with an environment variable as their credential source.
    """
    try:
        return _create_model_router_ai(max_monthly, extra_providers, free_only)
    except ImportError:
        logger.info("model-router-ai not installed, using SimpleRouter")
        return _create_simple_router()


def _create_model_router_ai(
    max_monthly: float | None,
    extra_providers: dict[str, str] | None,
    free_only: bool = False,
) -> Any:
    from model_router_ai import (
        CohereProvider,
        GeminiProvider,
        OpenAICompatProvider,
        ProviderRouter,
        discover_accounts,
        provider_definitions,
    )
    from model_router_ai.decorators import BudgetGuard, LatencyOptimizer

    definitions = {item["id"]: item for item in provider_definitions()}
    provider_classes = {
        "gemini": GeminiProvider,
        "cohere": CohereProvider,
    }

    base = ProviderRouter()
    added = 0
    for account in discover_accounts():
        provider_id = account["provider"]
        definition = definitions.get(provider_id)
        if not definition or (free_only and not definition["free_capable"]):
            continue

        credential_source = account.get("credential_source", "")
        if not credential_source.startswith("environment:"):
            continue
        env_var = credential_source.removeprefix("environment:")
        key = os.environ.get(env_var, "")
        if not key:
            continue

        if provider_id == "openrouter":
            provider = OpenAICompatProvider(provider_id, free_only=free_only)
        elif provider_id in provider_classes:
            provider = provider_classes[provider_id]()
        else:
            provider = OpenAICompatProvider(provider_id)

        base.add_provider(provider, api_key=key, account_name=account["id"])
        added += 1

    if extra_providers:
        for provider_name, env_var in extra_providers.items():
            key = os.environ.get(env_var, "")
            if not key:
                continue
            base.add_provider(
                OpenAICompatProvider(provider_name, free_only=free_only),
                api_key=key,
                account_name=f"{provider_name}-extra",
            )
            added += 1

    if added == 0:
        raise RuntimeError(
            "No authenticated providers found. Configure at least one supported provider credential."
        )

    router: Any = LatencyOptimizer(base)
    if max_monthly is not None:
        router = BudgetGuard(router, max_monthly=max_monthly)
    return router


@dataclass
class _Response:
    content: str = ""
    model: str = ""
    provider: str = ""
    usage: dict = dc_field(default_factory=dict)
    latency_ms: float = 0.0
    cost_usd: float = 0.0


class SimpleRouter:
    """Minimal provider-neutral fallback router."""

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
                    provider,
                    normalized,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as e:
                logger.warning("Provider %s failed: %s", provider["name"], e)
                errors.append((provider["name"], str(e)))
        raise RuntimeError(
            "All configured providers failed:\n"
            + "\n".join(f"  {n}: {e}" for n, e in errors)
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
        with urllib.request.urlopen(req, timeout=120) as resp:  # nosec B310
            result = json.loads(resp.read())
        content = result["choices"][0]["message"]["content"]
        return _Response(
            content=content,
            model=result.get("model", provider["model"]),
            provider=provider["name"],
            usage=result.get("usage", {}),
        )

    async def list_models(self) -> list:
        return []


def _create_simple_router() -> SimpleRouter:
    available = []
    for name, cfg in PROVIDERS.items():
        key = os.environ.get(cfg["env"], "")
        if key:
            available.append({**cfg, "key": key, "url": _endpoint(name)})
    if not available:
        raise RuntimeError(
            "No authenticated providers found. Configure at least one supported provider credential."
        )
    return SimpleRouter(available)


def _endpoint(name: str) -> str:
    return {
        "groq": "https://api.groq.com/openai/v1/chat/completions",
        "cerebras": "https://api.cerebras.ai/v1/chat/completions",
        "openrouter": "https://openrouter.ai/api/v1/chat/completions",
        "cohere": "https://api.cohere.com/v2/chat",
        "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "huggingface": "https://router.huggingface.co/v1/chat/completions",
    }[name]
