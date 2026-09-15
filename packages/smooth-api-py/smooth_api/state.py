from __future__ import annotations

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
    last_failure_time: float #epoch seconds (not ms)

class CircuitBreakerState:
    def __init__(
        self,
        config: CircuitBreakerConfig | None = None,
        on_state_change: Callable[[CircuitStateChangeEvent], Any] | None = None,
    ):
        self._config = config or CircuitBreakerConfig()
        self._on_state_change = on_state_change
        self._map: dict[str, CircuitEntry] = {}
        self._lock = threading.Lock()

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
                    loop.create_task(res)
                except RuntimeError:
                    asyncio.run(res)
        except Exception as ex:
            sys.stderr.write(f"[smoothAPI] Error in onCircuitStateChange hook: {ex}\n")

    # No lock needed here
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
        # Enforce a strict domain limit to bound memory usage
        if len(self._map) <= 1000:
            return
        keys_to_delete = [
            k for k, v in self._map.items()
            if v.state == 'CLOSED' and v.failure_count == 0
        ]
        for k in keys_to_delete:
            del self._map[k]

    def can_request(self, domain: str) -> bool:
        event = None
        with self._lock:
            entry = self._get_or_create(domain)
            if entry.state == 'CLOSED' or entry.state == 'HALF_OPEN':
                return True
            # cooldown_ms is in ms; time.time() is in seconds
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

    def get_state(self, domain: str) -> CircuitState:
        with self._lock:
            return self._get_or_create(domain).state