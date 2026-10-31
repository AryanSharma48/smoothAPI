from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional

CircuitState = Literal['CLOSED', 'OPEN', 'HALF_OPEN']
PartitionBy = Literal['host', 'host-and-path']
CircuitKeyFn = Callable[..., str]


@dataclass
class CircuitStateChangeEvent:
    domain: str
    from_state: CircuitState
    to_state: CircuitState
    failure_count: int
    failure_rate: Optional[float] = None
    key: Optional[str] = None

    @property
    def from_(self) -> CircuitState:
        return self.from_state

    @property
    def to(self) -> CircuitState:
        return self.to_state

    @property
    def failureCount(self) -> int:
        return self.failure_count

    @property
    def failureRate(self) -> Optional[float]:
        return self.failure_rate


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
    success_threshold: int = 1      # consecutive successes in HALF_OPEN to close
    failure_rate_threshold: Optional[float] = None  # 0.0 - 1.0 (e.g. 0.5 = 50%)
    window_size: int = 20           # sliding window size
    min_requests_in_window: int = 5 # min requests before failure rate applies
    partition_by: PartitionBy = 'host'  # 'host' or 'host-and-path'
    circuit_key_fn: Optional[CircuitKeyFn] = None

    # CamelCase aliases for cross-language compatibility
    failureThreshold: Optional[int] = None
    cooldownMs: Optional[int] = None
    successThreshold: Optional[int] = None
    failureRateThreshold: Optional[float] = None
    windowSize: Optional[int] = None
    minRequestsInWindow: Optional[int] = None
    partitionBy: Optional[PartitionBy] = None
    circuitKeyFn: Optional[CircuitKeyFn] = None

    def __post_init__(self):
        if self.failureThreshold is not None:
            self.failure_threshold = self.failureThreshold
        if self.cooldownMs is not None:
            self.cooldown_ms = self.cooldownMs
        if self.successThreshold is not None:
            self.success_threshold = self.successThreshold
        if self.failureRateThreshold is not None:
            self.failure_rate_threshold = self.failureRateThreshold
        if self.windowSize is not None:
            self.window_size = self.windowSize
        if self.minRequestsInWindow is not None:
            self.min_requests_in_window = self.minRequestsInWindow
        if self.partitionBy is not None:
            self.partition_by = self.partitionBy
        if self.circuitKeyFn is not None:
            self.circuit_key_fn = self.circuitKeyFn


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
class SuccessContext:
    url: str
    domain: str
    attempts: int
    duration_ms: float
    status: Optional[int] = None
    response: Optional[Any] = None

    @property
    def duration(self) -> float:
        """Duration in seconds."""
        return self.duration_ms / 1000.0


@dataclass
class FailureContext:
    url: str
    domain: str
    attempts: int
    duration_ms: float
    error: Optional[Any] = None
    status: Optional[int] = None
    response: Optional[Any] = None
    is_circuit_open: bool = False

    @property
    def duration(self) -> float:
        """Duration in seconds."""
        return self.duration_ms / 1000.0

    @property
    def isCircuitOpen(self) -> bool:
        return self.is_circuit_open


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
    on_success: Optional[Callable[[SuccessContext], Any]] = None
    on_failure: Optional[Callable[[FailureContext], Any]] = None
    onRetry: Optional[Callable[[RetryContext], Any]] = None
    onCircuitStateChange: Optional[Callable[[CircuitStateChangeEvent], Any]] = None
    onSuccess: Optional[Callable[[SuccessContext], Any]] = None
    onFailure: Optional[Callable[[FailureContext], Any]] = None

    def __post_init__(self):
        if self.on_retry is None and self.onRetry is not None:
            self.on_retry = self.onRetry
        if self.on_circuit_state_change is None and self.onCircuitStateChange is not None:
            self.on_circuit_state_change = self.onCircuitStateChange
        if self.on_success is None and self.onSuccess is not None:
            self.on_success = self.onSuccess
        if self.on_failure is None and self.onFailure is not None:
            self.on_failure = self.onFailure
