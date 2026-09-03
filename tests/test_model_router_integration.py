"""Tests for the model-router-ai integration boundary."""

from __future__ import annotations

import sys
import types

from personal_agent.router import _create_model_router_ai


def _fake_model_router(monkeypatch):
    calls: dict = {"providers": []}

    class FakeProviderRouter:
        def __init__(self):
            self.providers = calls["providers"]

        def add_provider(self, provider, *, api_key, account_name="default"):
            self.providers.append((provider, api_key, account_name))

    class FakeProvider:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class FakeWrapper:
        def __init__(self, wrapped, **kwargs):
            self.wrapped = wrapped
            self.kwargs = kwargs

    fake = types.ModuleType("model_router_ai")
    fake.ProviderRouter = FakeProviderRouter
    fake.OpenAICompatProvider = FakeProvider
    fake.GeminiProvider = FakeProvider
    fake.CohereProvider = FakeProvider
    fake.discover_accounts = lambda: [
        {
            "id": "groq-main",
            "provider": "groq",
            "credential_source": "environment:GROQ_API_KEY",
        },
        {
            "id": "openrouter-main",
            "provider": "openrouter",
            "credential_source": "environment:OPENROUTER_API_KEY",
        },
    ]
    fake.provider_definitions = lambda: [
        {"id": "groq", "free_capable": True},
        {"id": "openrouter", "free_capable": True},
    ]

    decorators = types.ModuleType("model_router_ai.decorators")
    decorators.BudgetGuard = FakeWrapper
    decorators.LatencyOptimizer = FakeWrapper
    monkeypatch.setitem(sys.modules, "model_router_ai", fake)
    monkeypatch.setitem(sys.modules, "model_router_ai.decorators", decorators)
    return calls


def test_routes_configured_accounts_and_preserves_account_identity(monkeypatch):
    calls = _fake_model_router(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "groq-secret")
    monkeypatch.setenv("OPENROUTER_API_KEY", "router-secret")

    router = _create_model_router_ai(None, None)

    assert [account for _, _, account in calls["providers"]] == [
        "groq-main",
        "openrouter-main",
    ]
    assert calls["providers"][0][1] == "groq-secret"
    assert isinstance(router.wrapped, calls.__class__) is False
    assert len(calls["providers"]) == 2


def test_free_only_registers_only_free_capable_accounts_and_filters_openrouter(monkeypatch):
    calls = _fake_model_router(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "groq-secret")
    monkeypatch.setenv("OPENROUTER_API_KEY", "router-secret")

    _create_model_router_ai(None, None, free_only=True)

    providers = calls["providers"]
    assert len(providers) == 2
    openrouter = next(provider for provider, _, _ in providers if provider.args == ("openrouter",))
    assert openrouter.kwargs["free_only"] is True


def test_extra_provider_is_supported_without_entering_the_worker_contract(monkeypatch):
    calls = _fake_model_router(monkeypatch)
    monkeypatch.setenv("CUSTOM_API_KEY", "custom-secret")

    _create_model_router_ai(None, {"custom": "CUSTOM_API_KEY"})

    provider, key, account = calls["providers"][-1]
    assert provider.args == ("custom",)
    assert key == "custom-secret"
    assert account == "custom-extra"


def test_monthly_budget_wraps_canonical_router(monkeypatch):
    _fake_model_router(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "groq-secret")

    router = _create_model_router_ai(300.0, None)

    assert router.kwargs["max_monthly"] == 300.0
