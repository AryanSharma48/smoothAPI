from __future__ import annotations

import asyncio
import inspect
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .config import CircuitBreakerConfig, CircuitState, CircuitStateChangeEvent


@dataclass
class CircuitEntry:
    state: CircuitState
    failure_count: int
    last_failure_time: float  # epoch seconds (not ms)
    consecutive_successes: int = 0
    probe_in_flight: bool = False
    probe_start_time: float = 0.0
    window: list[int] = field(default_factory=list)
    window_index: int = 0
    window_count: int = 0
    window_failures: int = 0


class CircuitBreakerState:
    def __init__(
        self,
        config: CircuitBreakerConfig | None = None,
        on_state_change: Callable[[CircuitStateChangeEvent], Any] | None = None,
    ):
        self._config = config or CircuitBreakerConfig()
        self._on_state_change = on_state_change
        self._map: dict[str, CircuitEntry] = {}
        self._lock = threading.RLock()

    def _transition(
        self,
        domain: str,
        entry: CircuitEntry,
        to: CircuitState,
        failure_rate: float | None = None,
    ) -> CircuitStateChangeEvent | None:
        from_state = entry.state
        if from_state != to:
            entry.state = to
            return CircuitStateChangeEvent(
                domain=domain,
                from_state=from_state,
                to_state=to,
                failure_count=entry.failure_count,
                failure_rate=failure_rate,
                key=domain,
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

    def _record_window_outcome(self, entry: CircuitEntry, success: bool) -> None:
        size = len(entry.window)
        if size == 0:
            return
        is_failure = 0 if success else 1
        if entry.window_count < size:
            entry.window[entry.window_index] = is_failure
            if is_failure == 1:
                entry.window_failures += 1
            entry.window_count += 1
        else:
            prev = entry.window[entry.window_index]
            if prev == 1 and is_failure == 0:
                entry.window_failures -= 1
            elif prev == 0 and is_failure == 1:
                entry.window_failures += 1
            entry.window[entry.window_index] = is_failure
        entry.window_index = (entry.window_index + 1) % size

    def _reset_window(self, entry: CircuitEntry) -> None:
        size = len(entry.window)
        entry.window = [0] * size
        entry.window_index = 0
        entry.window_count = 0
        entry.window_failures = 0

    def _get_or_create(self, domain: str) -> CircuitEntry:
        if domain not in self._map:
            self._cleanup()
            size = max(1, self._config.window_size or 20)
            self._map[domain] = CircuitEntry(
                state='CLOSED',
                failure_count=0,
                last_failure_time=0.0,
                consecutive_successes=0,
                probe_in_flight=False,
                window=[0] * size,
                window_index=0,
                window_count=0,
                window_failures=0,
            )
        return self._map[domain]

    def _cleanup(self) -> None:
        if len(self._map) <= 1000:
            return
        keys_to_delete = [
            k for k, v in self._map.items()
            if v.state == 'CLOSED' and v.failure_count == 0 and v.window_failures == 0
        ]
        for k in keys_to_delete:
            del self._map[k]

    def can_request(self, domain: str) -> bool:
        event = None
        now = time.time()
        with self._lock:
            entry = self._get_or_create(domain)
            if entry.state == 'CLOSED':
                return True
            elapsed = now - entry.last_failure_time
            if entry.state == 'OPEN':
                if elapsed > self._config.cooldown_ms / 1000:
                    event = self._transition(domain, entry, 'HALF_OPEN')
                    entry.consecutive_successes = 0
                    entry.probe_in_flight = True
                    entry.probe_start_time = now
                    allowed = True
                else:
                    allowed = False
            else:  # HALF_OPEN
                if entry.probe_in_flight:
                    # Lease expiry guard: if the in-flight probe has been running longer than cooldown_ms,
                    # it has leaked or timed out. Expire the lease so the circuit does not remain permanently blocked.
                    if now - entry.probe_start_time > self._config.cooldown_ms / 1000:
                        entry.probe_start_time = now
                        allowed = True
                    else:
                        allowed = False
                else:
                    entry.probe_in_flight = True
                    entry.probe_start_time = now
                    allowed = True
        if event:
            self._notify_state_change(event)
        return allowed

    def release_probe(self, domain: str) -> None:
        with self._lock:
            if domain in self._map:
                entry = self._map[domain]
                if entry.state == 'HALF_OPEN':
                    entry.probe_in_flight = False

    def record_success(self, domain: str) -> None:
        event = None
        with self._lock:
            entry = self._get_or_create(domain)
            entry.probe_in_flight = False
            self._record_window_outcome(entry, True)
            if entry.state == 'HALF_OPEN':
                entry.consecutive_successes += 1
                if entry.consecutive_successes >= self._config.success_threshold:
                    entry.failure_count = 0
                    entry.consecutive_successes = 0
                    self._reset_window(entry)
                    event = self._transition(domain, entry, 'CLOSED')
            elif entry.state == 'CLOSED':
                entry.failure_count = 0
        if event:
            self._notify_state_change(event)

    def record_failure(self, domain: str) -> None:
        event = None
        with self._lock:
            entry = self._get_or_create(domain)
            entry.probe_in_flight = False
            self._record_window_outcome(entry, False)
            entry.failure_count += 1

            if entry.state == 'HALF_OPEN':
                entry.consecutive_successes = 0
                entry.last_failure_time = time.time()
                event = self._transition(domain, entry, 'OPEN')
            else:
                consecutive_trip = entry.failure_count >= self._config.failure_threshold
                rate_trip = False
                failure_rate = None
                if (
                    self._config.failure_rate_threshold is not None
                    and entry.window_count >= self._config.min_requests_in_window
                ):
                    failure_rate = entry.window_failures / entry.window_count
                    if failure_rate >= self._config.failure_rate_threshold:
                        rate_trip = True

                if consecutive_trip or rate_trip:
                    entry.last_failure_time = time.time()
                    event = self._transition(domain, entry, 'OPEN', failure_rate=failure_rate)
        if event:
            self._notify_state_change(event)

    def get_state(self, domain: str) -> CircuitState:
        with self._lock:
            entry = self._get_or_create(domain)
            if entry.state == 'OPEN' and (time.time() - entry.last_failure_time) > self._config.cooldown_ms / 1000:
                return 'HALF_OPEN'
            return entry.state

    def get_stats(self, domain: str) -> dict[str, Any]:
        with self._lock:
            entry = self._get_or_create(domain)
            state = entry.state
            if state == 'OPEN' and (time.time() - entry.last_failure_time) > self._config.cooldown_ms / 1000:
                state = 'HALF_OPEN'
            rate = entry.window_failures / entry.window_count if entry.window_count > 0 else 0.0
            return {
                "state": state,
                "failure_count": entry.failure_count,
                "consecutive_successes": entry.consecutive_successes,
                "window_count": entry.window_count,
                "window_failures": entry.window_failures,
                "failure_rate": rate,
            }
