"""Tests for personal_agent.router."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from personal_agent.router import (
    PROVIDERS,
    SimpleRouter,
    _create_simple_router,
    create_router,
)


class TestProviders:
    def test_all_have_env_key(self):
        for name, cfg in PROVIDERS.items():
            assert "env" in cfg, f"{name} missing 'env' key"
            assert "name" in cfg
            assert "model" in cfg

    def test_expected_providers(self):
        expected = {"groq", "cerebras", "openrouter", "gemini", "cohere", "huggingface"}
        assert set(PROVIDERS.keys()) == expected


class TestSimpleRouter:
    def test_init(self):
        providers = [{"name": "test", "key": "k", "url": "http://x", "model": "m"}]
        r = SimpleRouter(providers)
        assert len(r._providers) == 1

    def test_initialize_is_noop(self):
        import asyncio
        r = SimpleRouter([])
        asyncio.run(r.initialize())

    def test_list_models_returns_empty(self):
        import asyncio
        r = SimpleRouter([])
        assert asyncio.run(r.list_models()) == []

    def test_all_providers_fail_raises(self):
        r = SimpleRouter(
            [
                {"name": "bad1", "key": "k", "url": "http://localhost:1", "model": "m"},
                {"name": "bad2", "key": "k", "url": "http://localhost:2", "model": "m"},
            ]
        )
        import asyncio
        with pytest.raises(RuntimeError, match="All configured providers failed"):
            asyncio.run(r.chat([{"role": "user", "content": "hi"}]))


class TestCreateSimpleRouter:
    def test_no_keys_raises(self):
        env = {cfg["env"]: "" for cfg in PROVIDERS.values()}
        with patch.dict(os.environ, env, clear=False):
            for key in env:
                os.environ.pop(key, None)
            with pytest.raises(RuntimeError, match="No authenticated providers found"):
                _create_simple_router()

    def test_cohere_key_creates_router(self):
        env_clear = {cfg["env"]: "" for cfg in PROVIDERS.values()}
        with patch.dict(os.environ, env_clear, clear=False):
            for k in env_clear:
                os.environ.pop(k, None)
            os.environ["COHERE_API_KEY"] = "test-key"
            r = _create_simple_router()
            assert isinstance(r, SimpleRouter)
            assert any(p["name"] == "cohere" for p in r._providers)

    def test_multiple_keys_creates_multi_provider(self):
        env_clear = {cfg["env"]: "" for cfg in PROVIDERS.values()}
        with patch.dict(os.environ, env_clear, clear=False):
            for k in env_clear:
                os.environ.pop(k, None)
            os.environ["COHERE_API_KEY"] = "key1"
            os.environ["GROQ_API_KEY"] = "key2"
            r = _create_simple_router()
            assert len(r._providers) == 2


class TestCreateRouter:
    def test_falls_back_to_simple_when_no_model_router_ai(self):
        with patch.dict(os.environ, {"COHERE_API_KEY": "test-key"}, clear=False), patch(
            "personal_agent.router._create_model_router_ai",
            side_effect=ImportError("no module"),
        ):
            r = create_router()
            assert isinstance(r, SimpleRouter)

    def test_no_keys_at_all_raises(self):
        env = {cfg["env"]: "" for cfg in PROVIDERS.values()}
        with patch.dict(os.environ, env, clear=False):
            for key in env:
                os.environ.pop(key, None)
            with patch(
                "personal_agent.router._create_model_router_ai",
                side_effect=ImportError("no module"),
            ):
                with pytest.raises(RuntimeError, match="No authenticated providers found"):
                    create_router()
