"""Tests for personal_agent.router."""

import os
from unittest.mock import patch

import pytest

from personal_agent.router import (
    FREE_PROVIDERS,
    PROVIDER_CONFIGS,
    SimpleFreeRouter,
    _create_simple_router,
    create_free_router,
)


class TestFreeProviders:
    def test_all_have_env_key(self):
        for name, cfg in FREE_PROVIDERS.items():
            assert "env" in cfg, f"{name} missing 'env' key"

    def test_expected_providers(self):
        expected = {"groq", "cerebras", "openrouter", "gemini", "cohere", "huggingface"}
        assert set(FREE_PROVIDERS.keys()) == expected


class TestProviderConfigs:
    def test_all_have_required_fields(self):
        for cfg in PROVIDER_CONFIGS:
            assert "name" in cfg
            assert "env" in cfg
            assert "url" in cfg
            assert "model" in cfg

    def test_cohere_marked(self):
        cohere = [c for c in PROVIDER_CONFIGS if c["name"] == "cohere"]
        assert len(cohere) == 1
        assert cohere[0].get("is_cohere") is True


class TestSimpleFreeRouter:
    def test_init(self):
        providers = [{"name": "test", "key": "k", "url": "http://x", "model": "m"}]
        r = SimpleFreeRouter(providers)
        assert len(r._providers) == 1

    @pytest.mark.asyncio
    async def test_initialize_is_noop(self):
        r = SimpleFreeRouter([])
        await r.initialize()

    @pytest.mark.asyncio
    async def test_list_models_returns_empty(self):
        r = SimpleFreeRouter([])
        assert await r.list_models() == []

    @pytest.mark.asyncio
    async def test_all_providers_fail_raises(self):
        r = SimpleFreeRouter([
            {"name": "bad1", "key": "k", "url": "http://localhost:1", "model": "m"},
            {"name": "bad2", "key": "k", "url": "http://localhost:2", "model": "m"},
        ])
        with pytest.raises(RuntimeError, match="All providers failed"):
            await r.chat([{"role": "user", "content": "hi"}])


class TestCreateSimpleRouter:
    def test_no_keys_raises(self):
        env = {cfg["env"]: "" for cfg in PROVIDER_CONFIGS}
        with patch.dict(os.environ, env, clear=False):
            for key in env:
                os.environ.pop(key, None)
            with pytest.raises(RuntimeError, match="No API keys found"):
                _create_simple_router()

    def test_cohere_key_creates_router(self):
        env_clear = {cfg["env"]: "" for cfg in PROVIDER_CONFIGS}
        with patch.dict(os.environ, env_clear, clear=False):
            for k in env_clear:
                os.environ.pop(k, None)
            os.environ["COHERE_API_KEY"] = "test-key"
            r = _create_simple_router()
            assert isinstance(r, SimpleFreeRouter)
            assert any(p["name"] == "cohere" for p in r._providers)

    def test_multiple_keys_creates_multi_provider(self):
        env_clear = {cfg["env"]: "" for cfg in PROVIDER_CONFIGS}
        with patch.dict(os.environ, env_clear, clear=False):
            for k in env_clear:
                os.environ.pop(k, None)
            os.environ["COHERE_API_KEY"] = "key1"
            os.environ["GROQ_API_KEY"] = "key2"
            r = _create_simple_router()
            assert len(r._providers) == 2


class TestCreateFreeRouter:
    def test_falls_back_to_simple_when_no_model_router_ai(self):
        with patch.dict(os.environ, {"COHERE_API_KEY": "test-key"}, clear=False), \
             patch("personal_agent.router._create_model_router_ai", side_effect=ImportError("no module")):
            r = create_free_router()
            assert isinstance(r, SimpleFreeRouter)

    def test_no_keys_at_all_raises(self):
        env = {cfg["env"]: "" for cfg in PROVIDER_CONFIGS}
        with patch.dict(os.environ, env, clear=False):
            for key in env:
                os.environ.pop(key, None)
            with patch("personal_agent.router._create_model_router_ai", side_effect=ImportError("no module")):
                with pytest.raises(RuntimeError, match="No API keys found"):
                    create_free_router()
