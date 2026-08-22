"""Tests for personal_agent.router."""

import os
from unittest.mock import patch

import pytest

from personal_agent.router import (
    FREE_PROVIDERS,
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


class TestSimpleFreeRouter:
    def test_init(self):
        r = SimpleFreeRouter("groq", "key123", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile")
        assert r._provider == "groq"
        assert r._api_key == "key123"

    @pytest.mark.asyncio
    async def test_initialize_is_noop(self):
        r = SimpleFreeRouter("groq", "key", "http://localhost", "model")
        await r.initialize()

    @pytest.mark.asyncio
    async def test_list_models_returns_empty(self):
        r = SimpleFreeRouter("groq", "key", "http://localhost", "model")
        assert await r.list_models() == []


class TestCreateSimpleRouter:
    def test_no_keys_raises(self):
        env = {k: "" for cfg in FREE_PROVIDERS.values() for k in [cfg["env"]]}
        with patch.dict(os.environ, env, clear=False):
            for key in env:
                os.environ.pop(key, None)
            with pytest.raises(RuntimeError, match="No API keys found"):
                _create_simple_router()

    def test_groq_key_creates_router(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}, clear=False):
            r = _create_simple_router()
            assert isinstance(r, SimpleFreeRouter)
            assert r._provider == "groq"

    def test_cerebras_key_creates_router(self):
        env = {"CEREBRAS_API_KEY": "test-key"}
        clear = {cfg["env"]: "" for cfg in FREE_PROVIDERS.values()}
        with patch.dict(os.environ, {**clear, **env}, clear=False):
            for k in clear:
                os.environ.pop(k, None)
            os.environ["CEREBRAS_API_KEY"] = "test-key"
            r = _create_simple_router()
            assert r._provider == "cerebras"


class TestCreateFreeRouter:
    def test_falls_back_to_simple_when_no_model_router_ai(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}, clear=False), \
             patch("personal_agent.router._create_model_router_ai", side_effect=ImportError("no module")):
            r = create_free_router()
            assert isinstance(r, SimpleFreeRouter)

    def test_no_keys_at_all_raises(self):
        env = {cfg["env"]: "" for cfg in FREE_PROVIDERS.values()}
        with patch.dict(os.environ, env, clear=False):
            for key in env:
                os.environ.pop(key, None)
            with patch("personal_agent.router._create_model_router_ai", side_effect=ImportError("no module")):
                with pytest.raises(RuntimeError, match="No API keys found"):
                    create_free_router()
