from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Literal

from .config import CircuitBreakerConfig

CircuitState = Literal['CLOSED', 'OPEN', 'HALF_OPEN']


@dataclass
class CircuitEntry:
    state: CircuitState
    failure_count: int
    last_failure_time: float #epoch seconds (not ms)

class CircuitBreakerState:
    def __init__(self, config: CircuitBreakerConfig | None = None):
        self._config = config or CircuitBreakerConfig()
        self._map: dict[str, CircuitEntry] = {}
        self._lock = threading.Lock()

    # No lock needed here
    def _get_or_create(self, domain: str) -> CircuitEntry:
        if domain not in self._map:
            self._map[domain] = CircuitEntry(
                state='CLOSED',
                failure_count=0,
                last_failure_time=0.0,
            )
        return self._map[domain]

    def can_request(self, domain: str) -> bool:
        with self._lock:
            entry = self._get_or_create(domain)
            if entry.state == 'CLOSED' or entry.state == 'HALF_OPEN':
                return True
            # cooldown_ms is in ms; time.time() is in seconds
            elapsed = time.time() - entry.last_failure_time
            if elapsed > self._config.cooldown_ms / 1000:
                entry.state = 'HALF_OPEN'
                return True
            return False

    def record_success(self, domain: str) -> None:
        with self._lock:
            entry = self._get_or_create(domain)
            entry.state = 'CLOSED'
            entry.failure_count = 0

    def record_failure(self, domain: str) -> None:
        with self._lock:
            entry = self._get_or_create(domain)
            entry.failure_count += 1
            if entry.state == 'HALF_OPEN':
                entry.state = 'OPEN'
                entry.last_failure_time = time.time()
                return
            if entry.failure_count >= self._config.failure_threshold:
                entry.state = 'OPEN'
                entry.last_failure_time = time.time()

    def get_state(self, domain: str) -> CircuitState:
        with self._lock:
            return self._get_or_create(domain).state