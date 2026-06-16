from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class BackoffConfig:
    base_delay: float = 0.1   # seconds, doubles each attempt before jitter
    max_delay: float = 30.0   # ceiling on the pre-jitter exponential
    max_retries: int = 3


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 3      # consecutive failures to trip OPEN
    cooldown_ms: int = 10_000       # time in OPEN before probing with HALF_OPEN


@dataclass
class ResilientConfig:
    backoff: BackoffConfig = field(default_factory=BackoffConfig)
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    # Returned immediately on an OPEN circuit, no network IO.
    fallback: Any = None
    # HTTP status codes that trigger a retry. Mirrors DEFAULT_RETRY_ON in index.ts.
    retry_on: list[int] = field(default_factory=lambda: [429, 500, 502, 503, 504])
    fallback_on_non_retryable: bool = False
    on_non_retryable_error: Callable[[int, str], None] | None = None
