import time
import pytest
from smooth_api import smooth_api, SmoothConfig
from smooth_api.config import BackoffConfig, CircuitBreakerConfig
from smooth_api.state import CircuitBreakerState


def test_sliding_window_failure_rate_threshold():
    breaker = CircuitBreakerState(
        CircuitBreakerConfig(
            failure_threshold=100,  # Consecutive threshold very high
            failure_rate_threshold=0.5,  # 50% failure rate
            window_size=10,
            min_requests_in_window=4,
        )
    )

    # 2 successes, 1 failure -> 1/3 (33%) -> below min requests (3 < 4) -> stays CLOSED
    breaker.record_success("api.example.com")
    breaker.record_success("api.example.com")
    breaker.record_failure("api.example.com")
    assert breaker.get_state("api.example.com") == "CLOSED"

    # 1 more failure -> 2 failures out of 4 (50%) -> trips OPEN!
    breaker.record_failure("api.example.com")
    assert breaker.get_state("api.example.com") == "OPEN"


def test_sliding_window_does_not_trip_below_threshold():
    breaker = CircuitBreakerState(
        CircuitBreakerConfig(
            failure_threshold=100,
            failure_rate_threshold=0.5,
            window_size=10,
            min_requests_in_window=4,
        )
    )

    # 3 successes, 1 failure -> 25% failure rate -> stays CLOSED
    breaker.record_success("api.example.com")
    breaker.record_success("api.example.com")
    breaker.record_success("api.example.com")
    breaker.record_failure("api.example.com")
    assert breaker.get_state("api.example.com") == "CLOSED"

    # 1 more success -> 1/5 (20%) -> stays CLOSED
    breaker.record_success("api.example.com")
    assert breaker.get_state("api.example.com") == "CLOSED"


def test_anti_flapping_success_threshold():
    breaker = CircuitBreakerState(
        CircuitBreakerConfig(
            failure_threshold=2,
            cooldown_ms=50,
            success_threshold=2,  # requires 2 consecutive successes
        )
    )

    breaker.record_failure("api.example.com")
    breaker.record_failure("api.example.com")
    assert breaker.get_state("api.example.com") == "OPEN"

    # Fast-forward cooldown
    entry = breaker._get_or_create("api.example.com")
    entry.last_failure_time = time.time() - 1.0

    # 1st probe enters HALF_OPEN
    assert breaker.can_request("api.example.com") is True
    assert breaker.get_state("api.example.com") == "HALF_OPEN"

    # 1st success -> STILL in HALF_OPEN (needs 2)
    breaker.record_success("api.example.com")
    assert breaker.get_state("api.example.com") == "HALF_OPEN"

    # 2nd probe enters
    assert breaker.can_request("api.example.com") is True

    # 2nd success -> transitions to CLOSED
    breaker.record_success("api.example.com")
    assert breaker.get_state("api.example.com") == "CLOSED"


def test_probe_failure_trips_back_to_open_immediately():
    breaker = CircuitBreakerState(
        CircuitBreakerConfig(
            failure_threshold=2,
            cooldown_ms=50,
            success_threshold=3,
        )
    )

    breaker.record_failure("api.example.com")
    breaker.record_failure("api.example.com")
    assert breaker.get_state("api.example.com") == "OPEN"

    entry = breaker._get_or_create("api.example.com")
    entry.last_failure_time = time.time() - 1.0

    # 1st probe succeeds
    assert breaker.can_request("api.example.com") is True
    breaker.record_success("api.example.com")
    assert breaker.get_state("api.example.com") == "HALF_OPEN"

    # 2nd probe starts
    assert breaker.can_request("api.example.com") is True

    # 2nd probe fails -> trips back to OPEN immediately
    breaker.record_failure("api.example.com")
    assert breaker.get_state("api.example.com") == "OPEN"


def test_single_inflight_probe_in_half_open():
    breaker = CircuitBreakerState(
        CircuitBreakerConfig(
            failure_threshold=2,
            cooldown_ms=50,
            success_threshold=2,
        )
    )

    breaker.record_failure("api.example.com")
    breaker.record_failure("api.example.com")

    entry = breaker._get_or_create("api.example.com")
    entry.last_failure_time = time.time() - 1.0

    # Caller 1 starts probing
    assert breaker.can_request("api.example.com") is True

    # Caller 2 tries concurrently while probe is in flight -> denied!
    assert breaker.can_request("api.example.com") is False

    # Caller 1 completes
    breaker.record_success("api.example.com")

    # Now caller 3 can probe
    assert breaker.can_request("api.example.com") is True


def test_route_partitioning_host_and_path():
    config = SmoothConfig(
        backoff=BackoffConfig(base_delay=0.01, max_retries=0),
        circuit_breaker=CircuitBreakerConfig(
            failure_threshold=2,
            cooldown_ms=60_000,
            partition_by="host-and-path",
        ),
        fallback={"fallback": True},
    )

    @smooth_api(config)
    def call_endpoint(url: str):
        if "broken-route" in url:
            raise RuntimeError("500 Server Error")
        return {"ok": True, "url": url}

    # Trip /broken-route
    for _ in range(2):
        try:
            call_endpoint("http://api.example.com/broken-route")
        except RuntimeError:
            pass

    # /broken-route receives fallback because circuit is OPEN for that path
    res_broken = call_endpoint("http://api.example.com/broken-route")
    assert res_broken == {"fallback": True}

    # /healthy-route on the EXACT SAME HOST succeeds!
    res_healthy = call_endpoint("http://api.example.com/healthy-route")
    assert res_healthy == {"ok": True, "url": "http://api.example.com/healthy-route"}


def test_custom_circuit_key_fn():
    config = SmoothConfig(
        backoff=BackoffConfig(base_delay=0.01, max_retries=0),
        circuit_breaker=CircuitBreakerConfig(
            failure_threshold=2,
            cooldown_ms=60_000,
            circuit_key_fn=lambda *args, **kwargs: kwargs.get("service", "default"),
        ),
        fallback={"fallback": True},
    )

    @smooth_api(config)
    def call_service(service: str = "default"):
        if service == "failing-service":
            raise RuntimeError("Service down")
        return {"status": "ok", "service": service}

    # Trip failing-service
    for _ in range(2):
        try:
            call_service(service="failing-service")
        except RuntimeError:
            pass

    # failing-service is tripped
    assert call_service(service="failing-service") == {"fallback": True}

    # billing-service is isolated and works fine
    assert call_service(service="billing-service") == {"status": "ok", "service": "billing-service"}


def test_get_stats_does_not_deadlock():
    breaker = CircuitBreakerState(CircuitBreakerConfig(failure_threshold=2))
    breaker.record_failure("api.example.com")

    # get_stats should acquire lock safely and return stats without deadlocking
    stats = breaker.get_stats("api.example.com")
    assert stats["state"] == "CLOSED"
    assert stats["failure_count"] == 1
    assert stats["failure_rate"] == 1.0


def test_leaked_probe_recovers_via_lease_expiry():
    breaker = CircuitBreakerState(CircuitBreakerConfig(failure_threshold=1, cooldown_ms=50))
    breaker.record_failure("api.example.com")
    assert breaker.get_state("api.example.com") == "OPEN"

    # Simulate cooldown expired
    entry = breaker._get_or_create("api.example.com")
    entry.last_failure_time = time.time() - 1.0

    # Probe 1 starts
    assert breaker.can_request("api.example.com") is True
    assert entry.probe_in_flight is True

    # Immediate concurrent probe is denied
    assert breaker.can_request("api.example.com") is False

    # Simulate probe crashed/leaked and cooldown_ms passed
    entry.probe_start_time = time.time() - 0.1
    # Lease expired: new probe is granted!
    assert breaker.can_request("api.example.com") is True


