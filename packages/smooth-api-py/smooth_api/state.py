from __future__ import annotations

import abc
import asyncio
import inspect
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from .config import CircuitBreakerConfig, CircuitState, CircuitStateChangeEvent


@dataclass
class CircuitEntry:
    state: CircuitState
    failure_count: int
    last_failure_time: float  # epoch seconds (not ms)


class CircuitBreakerStorage(abc.ABC):
    @abc.abstractmethod
    async def get_state(self, domain: str) -> CircuitEntry:
        """Retrieve current circuit entry state."""
        ...

    @abc.abstractmethod
    async def record_failure(
        self, domain: str, threshold: int, cooldown_ms: int
    ) -> CircuitState:
        """Record failure and return new circuit state."""
        ...

    @abc.abstractmethod
    async def record_success(self, domain: str) -> CircuitState:
        """Record success and return new circuit state."""
        ...


class InMemoryStorage(CircuitBreakerStorage):
    def __init__(self) -> None:
        self._map: dict[str, CircuitEntry] = {}
        self._lock = threading.Lock()

    def _cleanup(self) -> None:
        if len(self._map) <= 1000:
            return
        keys_to_delete = [
            k for k, v in self._map.items()
            if v.state == "CLOSED" and v.failure_count == 0
        ]
        for k in keys_to_delete:
            del self._map[k]

    def _get_or_create(self, domain: str) -> CircuitEntry:
        if domain not in self._map:
            self._cleanup()
            self._map[domain] = CircuitEntry(
                state="CLOSED",
                failure_count=0,
                last_failure_time=0.0,
            )
        return self._map[domain]

    async def get_state(self, domain: str) -> CircuitEntry:
        with self._lock:
            entry = self._get_or_create(domain)
            return CircuitEntry(
                state=entry.state,
                failure_count=entry.failure_count,
                last_failure_time=entry.last_failure_time,
            )

    async def record_failure(
        self, domain: str, threshold: int, cooldown_ms: int
    ) -> CircuitState:
        with self._lock:
            entry = self._get_or_create(domain)
            entry.failure_count += 1
            if entry.state == "HALF_OPEN" or entry.failure_count >= threshold:
                entry.state = "OPEN"
                entry.last_failure_time = time.time()
            return entry.state

    async def record_success(self, domain: str) -> CircuitState:
        with self._lock:
            entry = self._get_or_create(domain)
            entry.failure_count = 0
            entry.state = "CLOSED"
            return "CLOSED"


class RedisCircuitBreakerStorage(CircuitBreakerStorage):
    def __init__(self, redis_client: Any, key_prefix: str = "smoothapi:cb:") -> None:
        self._redis = redis_client
        self._key_prefix = key_prefix
        self._fallback = InMemoryStorage()

    def _get_key(self, domain: str) -> str:
        return f"{self._key_prefix}{domain}"

    async def get_state(self, domain: str) -> CircuitEntry:
        key = self._get_key(domain)
        lua = """
            local state = redis.call('HGET', KEYS[1], 'state')
            local failureCount = redis.call('HGET', KEYS[1], 'failure_count')
            local lastFailureTime = redis.call('HGET', KEYS[1], 'last_failure_time')
            return {
                state or 'CLOSED',
                failureCount or '0',
                lastFailureTime or '0'
            }
        """
        try:
            if inspect.iscoroutinefunction(getattr(self._redis, "eval", None)):
                res = await self._redis.eval(lua, 1, key)
            else:
                res = self._redis.eval(lua, 1, key)
            state = str(res[0]) if res and res[0] else "CLOSED"
            failure_count = int(res[1]) if res and len(res) > 1 else 0
            last_failure_time = float(res[2]) if res and len(res) > 2 else 0.0
            return CircuitEntry(
                state=state,  # type: ignore[arg-type]
                failure_count=failure_count,
                last_failure_time=last_failure_time,
            )
        except Exception:
            return await self._fallback.get_state(domain)

    async def record_failure(
        self, domain: str, threshold: int, cooldown_ms: int
    ) -> CircuitState:
        key = self._get_key(domain)
        now = time.time()
        lua = """
            local state = redis.call('HGET', KEYS[1], 'state') or 'CLOSED'
            local count = tonumber(redis.call('HINCRBY', KEYS[1], 'failure_count', 1))
            local now = tonumber(ARGV[1])
            local threshold = tonumber(ARGV[2])
            local cooldownMs = tonumber(ARGV[3])

            local newState = state
            if state == 'HALF_OPEN' or count >= threshold then
                newState = 'OPEN'
                redis.call('HSET', KEYS[1], 'state', 'OPEN')
                redis.call('HSET', KEYS[1], 'last_failure_time', tostring(now))
                local ttlSec = math.ceil((cooldownMs * 2) / 1000)
                if ttlSec > 0 then
                    redis.call('EXPIRE', KEYS[1], ttlSec)
                end
            end
            return newState
        """
        try:
            if inspect.iscoroutinefunction(getattr(self._redis, "eval", None)):
                result = await self._redis.eval(lua, 1, key, now, threshold, cooldown_ms)
            else:
                result = self._redis.eval(lua, 1, key, now, threshold, cooldown_ms)
            return str(result)  # type: ignore[return-value]
        except Exception:
            return await self._fallback.record_failure(domain, threshold, cooldown_ms)

    async def record_success(self, domain: str) -> CircuitState:
        key = self._get_key(domain)
        lua = """
            redis.call('HSET', KEYS[1], 'state', 'CLOSED')
            redis.call('HSET', KEYS[1], 'failure_count', '0')
            return 'CLOSED'
        """
        try:
            if inspect.iscoroutinefunction(getattr(self._redis, "eval", None)):
                result = await self._redis.eval(lua, 1, key)
            else:
                result = self._redis.eval(lua, 1, key)
            return str(result)  # type: ignore[return-value]
        except Exception:
            return await self._fallback.record_success(domain)


class CircuitBreakerState:
    def __init__(
        self,
        config: CircuitBreakerConfig | None = None,
        on_state_change: Callable[[CircuitStateChangeEvent], Any] | None = None,
        storage: CircuitBreakerStorage | None = None,
    ):
        self._config = config or CircuitBreakerConfig()
        self._on_state_change = on_state_change
        self._storage = storage or InMemoryStorage()
        self._map: dict[str, CircuitEntry] = {}
        self._lock = threading.Lock()

    @property
    def storage(self) -> CircuitBreakerStorage:
        return self._storage

    def _transition(self, domain: str, entry: CircuitEntry, to: CircuitState) -> CircuitStateChangeEvent | None:
        from_state = entry.state
        if from_state != to:
            entry.state = to
            return CircuitStateChangeEvent(
                domain=domain,
                from_state=from_state,
                to_state=to,
                failure_count=entry.failure_count,
            )
        return None

    def _notify_state_change(self, event: CircuitStateChangeEvent | None) -> None:
        if event is None or self._on_state_change is None:
            return
        try:
            res = self._on_state_change(event)
            if inspect.iscoroutine(res):
                try:
                    loop = asyncio.get_running_loop()
                    task = loop.create_task(res)
                    def _handle_task_done(t: asyncio.Task) -> None:
                        if not t.cancelled() and t.exception():
                            sys.stderr.write(f"[smoothAPI] Error in async onCircuitStateChange hook: {t.exception()}\n")
                    task.add_done_callback(_handle_task_done)
                except RuntimeError:
                    asyncio.run(res)
        except Exception as ex:
            sys.stderr.write(f"[smoothAPI] Error in onCircuitStateChange hook: {ex}\n")

    def _get_or_create(self, domain: str) -> CircuitEntry:
        if domain not in self._map:
            self._cleanup()
            self._map[domain] = CircuitEntry(
                state='CLOSED',
                failure_count=0,
                last_failure_time=0.0,
            )
        return self._map[domain]

    def _cleanup(self) -> None:
        if len(self._map) <= 1000:
            return
        keys_to_delete = [
            k for k, v in self._map.items()
            if v.state == 'CLOSED' and v.failure_count == 0
        ]
        for k in keys_to_delete:
            del self._map[k]

    def _schedule_async(self, coro: Any) -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro)
        except RuntimeError:
            try:
                asyncio.run(coro)
            except Exception:
                pass

    def can_request(self, domain: str) -> bool:
        event = None
        with self._lock:
            entry = self._get_or_create(domain)
            if entry.state == 'CLOSED' or entry.state == 'HALF_OPEN':
                return True
            elapsed = time.time() - entry.last_failure_time
            if elapsed > self._config.cooldown_ms / 1000:
                event = self._transition(domain, entry, 'HALF_OPEN')
                allowed = True
            else:
                allowed = False
        if event:
            self._notify_state_change(event)
        return allowed

    async def can_request_async(self, domain: str) -> bool:
        remote_entry = await self._storage.get_state(domain)
        event = None
        with self._lock:
            entry = self._get_or_create(domain)
            entry.state = remote_entry.state
            entry.failure_count = remote_entry.failure_count
            entry.last_failure_time = remote_entry.last_failure_time

            if entry.state == 'CLOSED' or entry.state == 'HALF_OPEN':
                return True
            elapsed = time.time() - entry.last_failure_time
            if elapsed > self._config.cooldown_ms / 1000:
                event = self._transition(domain, entry, 'HALF_OPEN')
                allowed = True
            else:
                allowed = False
        if event:
            self._notify_state_change(event)
        return allowed

    def record_success(self, domain: str) -> None:
        event = None
        with self._lock:
            entry = self._get_or_create(domain)
            entry.failure_count = 0
            event = self._transition(domain, entry, 'CLOSED')
        if event:
            self._notify_state_change(event)
        self._schedule_async(self._storage.record_success(domain))

    async def record_success_async(self, domain: str) -> None:
        new_state = await self._storage.record_success(domain)
        event = None
        with self._lock:
            entry = self._get_or_create(domain)
            entry.failure_count = 0
            event = self._transition(domain, entry, new_state)
        if event:
            self._notify_state_change(event)

    def record_failure(self, domain: str) -> None:
        event = None
        with self._lock:
            entry = self._get_or_create(domain)
            entry.failure_count += 1
            if entry.state == 'HALF_OPEN':
                event = self._transition(domain, entry, 'OPEN')
                entry.last_failure_time = time.time()
            elif entry.failure_count >= self._config.failure_threshold:
                event = self._transition(domain, entry, 'OPEN')
                entry.last_failure_time = time.time()
        if event:
            self._notify_state_change(event)
        self._schedule_async(
            self._storage.record_failure(
                domain, self._config.failure_threshold, self._config.cooldown_ms
            )
        )

    async def record_failure_async(self, domain: str) -> None:
        new_state = await self._storage.record_failure(
            domain, self._config.failure_threshold, self._config.cooldown_ms
        )
        event = None
        with self._lock:
            entry = self._get_or_create(domain)
            entry.failure_count += 1
            entry.last_failure_time = time.time()
            event = self._transition(domain, entry, new_state)
        if event:
            self._notify_state_change(event)

    def get_state(self, domain: str) -> CircuitState:
        with self._lock:
            return self._get_or_create(domain).state

    async def get_state_async(self, domain: str) -> CircuitState:
        remote_entry = await self._storage.get_state(domain)
        with self._lock:
            entry = self._get_or_create(domain)
            entry.state = remote_entry.state
            entry.failure_count = remote_entry.failure_count
            entry.last_failure_time = remote_entry.last_failure_time
            return entry.state
