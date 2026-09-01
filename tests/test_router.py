"""Tests for personal_agent.router."""

import os
from unittest.mock import patch

import pytest

from personal_agent.router import (
    PROVIDERS,
    SimpleRouter,
    _create_simple_router,
    _endpoint,
    create_router,
)


class TestProviders:
    def test_expected_providers(self):
        assert set(PROVIDERS) == {
            "groq", "cerebras", "openrouter", "gemini", "cohere", "huggingface"
        }

    def test_provider_configs_have_required_fields(self):
        for name, cfg in PROVIDERS.items():
            assert cfg["name"] == name
            assert cfg["env"]
            assert "model" in cfg

    def test_endpoints_are_defined(self):
        for name in PROVIDERS:
            assert _endpoint(name).startswith("https://")


class TestSimpleRouter:
    def test_init(self):
        providers = [{"name": "test", "key": "k", "url": "http://x", "model": "m"}]
        router = SimpleRouter(providers)
        assert router._providers == providers

    @pytest.mark.asyncio
    async def test_initialize_is_noop(self):
        await SimpleRouter([]).initialize()

    @pytest.mark.asyncio
    async def test_list_models_returns_empty(self):
        assert await SimpleRouter([]).list_models() == []

    @pytest.mark.asyncio
    async def test_all_providers_fail_raises(self):
        router = SimpleRouter([
            {"name": "bad1", "key": "k", "url": "http://localhost:1", "model": "m"},
            {"name": "bad2", "key": "k", "url": "http://localhost:2", "model": "m"},
        ])
        with pytest.raises(RuntimeError, match="All configured providers failed"):
            await router.chat([{"role": "user", "content": "hi"}])


class TestCreateSimpleRouter:
    def test_no_keys_raises(self):
        env = {cfg["env"]: "" for cfg in PROVIDERS.values()}
        with patch.dict(os.environ, env, clear=False):
            for key in env:
                os.environ.pop(key, None)
            with pytest.raises(RuntimeError, match="No authenticated providers found"):
                _create_simple_router()

    def test_single_key_creates_router(self):
        env = {cfg["env"]: "" for cfg in PROVIDERS.values()}
        with patch.dict(os.environ, env, clear=False):
            for key in env:
                os.environ.pop(key, None)
            os.environ["GROQ_API_KEY"] = "test-key"
            router = _create_simple_router()
            assert isinstance(router, SimpleRouter)
            assert router._providers[0]["name"] == "groq"
            assert router._providers[0]["key"] == "test-key"

    def test_multiple_keys_creates_multi_provider_router(self):
        env = {cfg["env"]: "" for cfg in PROVIDERS.values()}
        with patch.dict(os.environ, env, clear=False):
            for key in env:
                os.environ.pop(key, None)
            os.environ["GROQ_API_KEY"] = "key1"
            os.environ["CEREBRAS_API_KEY"] = "key2"
            router = _create_simple_router()
            assert isinstance(router, SimpleRouter)
            assert {p["name"] for p in router._providers} == {"groq", "cerebras"}


class TestCreateRouter:
    def test_falls_back_to_simple_when_model_router_unavailable(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}, clear=False), \
             patch("personal_agent.router._create_model_router_ai", side_effect=ImportError("no module")):
            router = create_router()
            assert isinstance(router, SimpleRouter)

    def test_no_keys_at_all_raises(self):
        env = {cfg["env"]: "" for cfg in PROVIDERS.values()}
        with patch.dict(os.environ, env, clear=False):
            for key in env:
                os.environ.pop(key, None)
            with patch("personal_agent.router._create_model_router_ai", side_effect=ImportError("no module")):
                with pytest.raises(RuntimeError, match="No authenticated providers found"):
                    create_router()
