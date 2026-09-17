from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional

CircuitState = Literal['CLOSED', 'OPEN', 'HALF_OPEN']


@dataclass
class CircuitStateChangeEvent:
    domain: str
    from_state: CircuitState
    to_state: CircuitState
    failure_count: int

    @property
    def from_(self) -> CircuitState:
        return self.from_state

    @property
    def to(self) -> CircuitState:
        return self.to_state

    @property
    def failureCount(self) -> int:
        return self.failure_count


@dataclass
class RetryContext:
    attempt: int
    max_retries: int
    delay_ms: float
    domain: str
    url: str = ""
    status: Optional[int] = None
    error: Optional[Exception] = None

    @property
    def delay(self) -> float:
        """Delay in seconds."""
        return self.delay_ms / 1000.0


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
    # Maximum duration in milliseconds before a request attempt is aborted.
    timeout_ms: Optional[int] = None
    # Lifecycle event hooks
    on_retry: Optional[Callable[[RetryContext], Any]] = None
    on_circuit_state_change: Optional[Callable[[CircuitStateChangeEvent], Any]] = None
    onRetry: Optional[Callable[[RetryContext], Any]] = None
    onCircuitStateChange: Optional[Callable[[CircuitStateChangeEvent], Any]] = None

    def __post_init__(self):
        if self.on_retry is None and self.onRetry is not None:
            self.on_retry = self.onRetry
        if self.on_circuit_state_change is None and self.onCircuitStateChange is not None:
            self.on_circuit_state_change = self.onCircuitStateChange
