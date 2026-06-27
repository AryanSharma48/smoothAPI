from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class BackoffConfig:
    base_delay: float = 0.1   # seconds, doubles each attempt before jitter
    max_delay: float = 30.0   # ceiling on the pre-jitter exponential
    max_retries: int = 3


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 3      # consecutive failures to trip OPEN
    cooldown_ms: int = 10_000       # time in OPEN before probing with HALF_OPEN


# A key function receives (*args, **kwargs) of the wrapped function and must
# return a hashable key string, or None to opt this call out of deduplication.
KeyFn = Callable[..., Optional[str]]


@dataclass
class DeduplicationConfig:
    """
    Configuration for request deduplication.

    When attached to ``SmoothConfig``, in-flight calls that share the same
    *key* are coalesced: only the first caller actually runs the function; all
    others await the same coroutine and receive its result (or exception).

    Attributes
    ----------
    key_fn:
        A callable that receives the same ``*args`` and ``**kwargs`` passed to
        the decorated function and returns a :class:`str` key (or ``None`` to
        opt this specific invocation out of deduplication).  Defaults to a
        function that joins the positional arguments with ``':'``.
    """
    key_fn: Optional[KeyFn] = None


@dataclass
class SmoothConfig:
    backoff: BackoffConfig = field(default_factory=BackoffConfig)
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    # Returned immediately on an OPEN circuit, no network IO.
    fallback: Any = None
    # HTTP status codes that trigger a retry. Mirrors DEFAULT_RETRY_ON in index.ts.
    retry_on: list[int] = field(default_factory=lambda: [429, 500, 502, 503, 504])
    fallback_on_non_retryable: bool = False
    on_non_retryable_error: Callable[[int, str], None] | None = None
    # When set, enables request deduplication for async-decorated functions.
    deduplication: Optional[DeduplicationConfig] = None
