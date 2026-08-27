"""Provider/account/model/worker fabric used by the model gateway."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class WorkerStatus(str, Enum):
    SUCCESS = "success"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXHAUSTED = "quota_exhausted"
    AUTH_FAILED = "auth_failed"
    MODEL_UNAVAILABLE = "model_unavailable"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    INVALID_REQUEST = "invalid_request"
    FAILED = "failed"


@dataclass(frozen=True)
class Provider:
    id: str
    endpoint: str
    kind: str = "openai-compatible"


@dataclass(frozen=True)
class Account:
    id: str
    provider_id: str
    api_key_env: str
    api_key_override: str | None = None

    def api_key(self) -> str:
        return self.api_key_override if self.api_key_override is not None else os.environ.get(self.api_key_env, "")


@dataclass(frozen=True)
class Model:
    id: str
    capabilities: frozenset[str] = frozenset()
    context_length: int | None = None


@dataclass
class WorkerResult:
    status: WorkerStatus
    content: str = ""
    model: str = ""
    provider: str = ""
    account: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    error: str = ""
    retry_after: float | None = None
    quota_reset: float | None = None


class WorkerProtocol(Protocol):
    id: str
    provider: Provider
    account: Account
    model: Model

    def capabilities(self) -> frozenset[str]: ...
    def available(self) -> bool: ...
    async def execute(self, messages: list[dict[str, str]], **kwargs: Any) -> WorkerResult: ...


class ModelWorker:
    """Concrete route: provider + account + model."""

    def __init__(self, worker_id: str, provider: Provider, account: Account, model: Model,
                 *, enabled: bool = True, timeout: float = 120.0,
                 headers: dict[str, str] | None = None) -> None:
        self.id = worker_id
        self.provider = provider
        self.account = account
        self.model = model
        self.enabled = enabled
        self.timeout = timeout
        self.headers = headers or {}
        self._unavailable_until = 0.0
        self._last_error = ""

    def capabilities(self) -> frozenset[str]:
        return self.model.capabilities

    def available(self) -> bool:
        if not self.enabled or not self.account.api_key():
            return False
        return time.time() >= self._unavailable_until

    @property
    def unavailable_until(self) -> float:
        return self._unavailable_until

    def mark_unavailable(self, until: float | None = None, error: str = "") -> None:
        target = until if until is not None else time.time() + 60.0
        self._unavailable_until = max(time.time() + 0.001, target)
        self._last_error = error

    def mark_available(self) -> None:
        self._unavailable_until = 0.0
        self._last_error = ""

    async def execute(self, messages: list[dict[str, str]], **kwargs: Any) -> WorkerResult:
        if not self.available():
            return WorkerResult(
                status=WorkerStatus.QUOTA_EXHAUSTED,
                provider=self.provider.id, account=self.account.id, model=self.model.id,
                error=self._last_error or "worker unavailable", quota_reset=self._unavailable_until or None,
            )
        return await asyncio.to_thread(self._execute_sync, messages, kwargs)

    def _execute_sync(self, messages: list[dict[str, str]], kwargs: dict[str, Any]) -> WorkerResult:
        body: dict[str, Any] = {"model": self.model.id, "messages": messages}
        for key in ("temperature", "max_tokens", "stream"):
            if key in kwargs and kwargs[key] is not None:
                body[key] = kwargs[key]
        headers = {"Content-Type": "application/json", **self.headers}
        headers["Authorization"] = f"Bearer {self.account.api_key()}"
        request = urllib.request.Request(
            self.provider.endpoint, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST"
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            elapsed = (time.monotonic() - started) * 1000
            choice = payload.get("choices", [{}])[0]
            content = choice.get("message", {}).get("content", "")
            return WorkerResult(
                status=WorkerStatus.SUCCESS, content=content,
                model=payload.get("model", self.model.id), provider=self.provider.id,
                account=self.account.id, usage=payload.get("usage", {}) or {}, latency_ms=elapsed,
            )
        except urllib.error.HTTPError as exc:
            elapsed = (time.monotonic() - started) * 1000
            raw = exc.read().decode("utf-8", errors="replace")
            status, retry_after, quota_reset = self._classify_http_error(exc, raw)
            if status in (WorkerStatus.RATE_LIMITED, WorkerStatus.QUOTA_EXHAUSTED):
                until = quota_reset if quota_reset is not None else time.time() + max(retry_after or 60.0, 1.0)
                self.mark_unavailable(until, raw)
            return WorkerResult(
                status=status, provider=self.provider.id, account=self.account.id, model=self.model.id,
                latency_ms=elapsed, error=raw, retry_after=retry_after, quota_reset=quota_reset,
            )
        except urllib.error.URLError as exc:
            return WorkerResult(status=WorkerStatus.NETWORK_ERROR, provider=self.provider.id,
                                 account=self.account.id, model=self.model.id, error=str(exc))
        except TimeoutError as exc:
            return WorkerResult(status=WorkerStatus.TIMEOUT, provider=self.provider.id,
                                 account=self.account.id, model=self.model.id, error=str(exc))
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            return WorkerResult(status=WorkerStatus.FAILED, provider=self.provider.id,
                                 account=self.account.id, model=self.model.id, error=str(exc))
        except Exception as exc:  # pragma: no cover
            logger.debug("worker %s failed", self.id, exc_info=True)
            return WorkerResult(status=WorkerStatus.FAILED, provider=self.provider.id,
                                 account=self.account.id, model=self.model.id, error=str(exc))

    @staticmethod
    def _classify_http_error(exc: urllib.error.HTTPError, raw: str) -> tuple[WorkerStatus, float | None, float | None]:
        retry_after: float | None = None
        quota_reset: float | None = None
        header = exc.headers.get("Retry-After")
        if header:
            try:
                retry_after = float(header)
            except ValueError:
                pass
        reset = exc.headers.get("X-RateLimit-Reset")
        if reset:
            try:
                value = float(reset)
                quota_reset = value / 1000 if value > 10_000_000_000 else value
            except ValueError:
                pass
        lowered = raw.lower()
        if exc.code == 429:
            status = WorkerStatus.QUOTA_EXHAUSTED if any(x in lowered for x in ("free-models-per-day", "quota", "daily")) else WorkerStatus.RATE_LIMITED
            return status, retry_after, quota_reset
        if exc.code in (401, 403):
            return WorkerStatus.AUTH_FAILED, retry_after, quota_reset
        if exc.code in (400, 422):
            return WorkerStatus.INVALID_REQUEST, retry_after, quota_reset
        if exc.code in (404, 410):
            return WorkerStatus.MODEL_UNAVAILABLE, retry_after, quota_reset
        return WorkerStatus.FAILED, retry_after, quota_reset


class WorkerPool:
    def __init__(self, workers: list[ModelWorker] | None = None) -> None:
        self.workers = list(workers or [])

    def add(self, worker: ModelWorker) -> None:
        self.workers.append(worker)

    def eligible(self, *, model: str | None = None,
                 capabilities: frozenset[str] = frozenset()) -> list[ModelWorker]:
        return [w for w in self.workers if w.available()
                and (model is None or w.model.id == model)
                and capabilities.issubset(w.capabilities())]


class Arbiter:
    """Select workers and fail over across independent routes."""

    def __init__(self, pool: WorkerPool) -> None:
        self.pool = pool

    async def execute(self, messages: list[dict[str, str]], *, model: str | None = None,
                      capabilities: frozenset[str] = frozenset(), **kwargs: Any) -> WorkerResult:
        candidates = self.pool.eligible(model=model, capabilities=capabilities)
        if not candidates:
            raise RuntimeError("No available workers")
        errors: list[str] = []
        for worker in candidates:
            result = await worker.execute(messages, **kwargs)
            if result.status is WorkerStatus.SUCCESS:
                return result
            errors.append(f"{worker.id}: {result.status.value}: {result.error}")
        raise RuntimeError("No worker succeeded:\n" + "\n".join(errors))


def workers_from_config(config: list[dict[str, Any]]) -> WorkerPool:
    providers: dict[str, Provider] = {}
    accounts: dict[tuple[str, str], Account] = {}
    models: dict[str, Model] = {}
    pool = WorkerPool()
    for item in config:
        if not item.get("enabled", True):
            continue
        provider_id = item["provider"]
        account_id = item.get("account", "default")
        model_id = item["model"]
        provider = providers.setdefault(provider_id, Provider(provider_id, item["endpoint"], item.get("kind", "openai-compatible")))
        account_key = (provider_id, account_id)
        account = accounts.setdefault(account_key, Account(account_id, provider_id, item["api_key_env"]))
        model = models.setdefault(model_id, Model(model_id, frozenset(item.get("capabilities", ["chat"])), item.get("context_length")))
        pool.add(ModelWorker(item.get("id", f"{provider_id}/{account_id}/{model_id}"), provider, account, model, timeout=float(item.get("timeout", 120))))
    return pool


def load_worker_config(env_var: str = "FLOSSWARE_WORKERS_CONFIG") -> list[dict[str, Any]]:
    value = os.environ.get(env_var, "").strip()
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid {env_var}: {exc}") from exc
    if not isinstance(parsed, list):
        raise RuntimeError(f"{env_var} must contain a JSON array")
    return parsed
