"""Tests for provider/account/model/worker routing."""

import asyncio
import json
import os
import time
from unittest.mock import patch

import pytest

from personal_agent.model_fabric import (
    Account,
    Arbiter,
    Model,
    ModelWorker,
    Provider,
    WorkerPool,
    WorkerResult,
    WorkerStatus,
    load_worker_config,
    workers_from_config,
)


@pytest.fixture
def providers():
    provider = Provider("openrouter", "https://example.invalid/v1/chat/completions")
    account_a = Account("flossware", "openrouter", "TEST_KEY_A")
    account_b = Account("ncrr", "openrouter", "TEST_KEY_B")
    model = Model("test-model", frozenset({"chat"}))
    return provider, account_a, account_b, model


def test_worker_identity_is_provider_account_model(providers):
    provider, account, _, model = providers
    worker = ModelWorker("w1", provider, account, model)
    assert worker.provider.id == "openrouter"
    assert worker.account.id == "flossware"
    assert worker.model.id == "test-model"
    assert worker.capabilities() == frozenset({"chat"})


def test_pool_keeps_accounts_independent(providers):
    provider, account_a, account_b, model = providers
    with patch.dict(os.environ, {"TEST_KEY_A": "a", "TEST_KEY_B": "b"}, clear=False):
        first = ModelWorker("a", provider, account_a, model)
        second = ModelWorker("b", provider, account_b, model)
        first.mark_unavailable(time.time() + 60, "quota exhausted")
        pool = WorkerPool([first, second])
        assert [w.id for w in pool.eligible(model="test-model")] == ["b"]


@pytest.mark.asyncio
async def test_arbiter_fails_over_to_second_account(providers):
    provider, account_a, account_b, model = providers
    with patch.dict(os.environ, {"TEST_KEY_A": "a", "TEST_KEY_B": "b"}, clear=False):
        first = ModelWorker("a", provider, account_a, model)
        second = ModelWorker("b", provider, account_b, model)

        async def first_execute(messages, **kwargs):
            return WorkerResult(status=WorkerStatus.QUOTA_EXHAUSTED, provider="openrouter", account="flossware", model="test-model", error="daily quota")

        async def second_execute(messages, **kwargs):
            return WorkerResult(status=WorkerStatus.SUCCESS, content="ok", provider="openrouter", account="ncrr", model="test-model")

        first.execute = first_execute
        second.execute = second_execute
        result = await Arbiter(WorkerPool([first, second])).execute([{"role": "user", "content": "hi"}])
        assert result.content == "ok"
        assert result.account == "ncrr"


def test_explicit_config_supports_multiple_accounts():
    config = [
        {"id": "or/a/model", "provider": "openrouter", "account": "a", "model": "model", "endpoint": "http://example/a", "api_key_env": "KEY_A"},
        {"id": "or/b/model", "provider": "openrouter", "account": "b", "model": "model", "endpoint": "http://example/b", "api_key_env": "KEY_B"},
    ]
    pool = workers_from_config(config)
    assert [w.account.id for w in pool.workers] == ["a", "b"]
    assert len(pool.workers) == 2


def test_disabled_worker_is_not_registered():
    config = [{"id": "disabled", "provider": "p", "account": "a", "model": "m", "endpoint": "http://example", "api_key_env": "KEY", "enabled": False}]
    assert workers_from_config(config).workers == []


def test_default_config_is_empty(monkeypatch):
    monkeypatch.delenv("FLOSSWARE_WORKERS_CONFIG", raising=False)
    assert load_worker_config() == []


def test_config_requires_array(monkeypatch):
    monkeypatch.setenv("FLOSSWARE_WORKERS_CONFIG", json.dumps({"worker": 1}))
    with pytest.raises(RuntimeError, match="JSON array"):
        load_worker_config()


def test_http_429_daily_quota_classification():
    from urllib.error import HTTPError
    from io import BytesIO

    exc = HTTPError("http://example", 429, "rate", {"X-RateLimit-Reset": "1787875200000"}, BytesIO(b'{"message":"free-models-per-day"}'))
    status, retry_after, reset = ModelWorker._classify_http_error(exc, '{"message":"free-models-per-day"}')
    assert status is WorkerStatus.QUOTA_EXHAUSTED
    assert reset == 1787875200.0


def test_reset_time_reenables_worker(providers):
    provider, account, _, model = providers
    with patch.dict(os.environ, {"TEST_KEY_A": "a"}, clear=False):
        worker = ModelWorker("w", provider, account, model)
        worker.mark_unavailable(time.time() - 1, "expired")
        assert worker.available()
