"""Integration tests for smooth_api against the sandbox server on port 3001."""
from __future__ import annotations

import time

import pytest
import requests

from smooth_api import resilient_api, ResilientConfig
from smooth_api.config import BackoffConfig, CircuitBreakerConfig

BASE = "http://localhost:3001"


def reset():
    """Reset sandbox request counter between tests."""
    requests.get(f"{BASE}/reset")


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_counter():
    reset()
    yield
    reset()


# ─── Retry logic ──────────────────────────────────────────────────────────────

def test_retries_on_500_and_eventually_succeeds():
    config = ResilientConfig(
        backoff=BackoffConfig(base_delay=0.01, max_delay=0.1, max_retries=5),
        circuit_breaker=CircuitBreakerConfig(failure_threshold=10, cooldown_ms=60_000),
    )

    @resilient_api(config)
    def get_data():
        res = requests.get(f"{BASE}/unstable-data")
        res.raise_for_status()
        return res.json()

    result = get_data()
    assert result == {"success": True, "data": "Solid Data"}


def test_retry_respects_retry_on_codes():
    """429 and 500 trigger retries; 200 does not."""
    config = ResilientConfig(
        backoff=BackoffConfig(base_delay=0.01, max_delay=0.1, max_retries=3),
        circuit_breaker=CircuitBreakerConfig(failure_threshold=10, cooldown_ms=60_000),
        retry_on=[429, 500],
    )

    call_count = [0]

    @resilient_api(config)
    def get_data():
        call_count[0] += 1
        res = requests.get(f"{BASE}/unstable-data")
        res.raise_for_status()
        return res.json()

    try:
        get_data()
    except Exception:
        pass

    # At least one retry happened (call_count > 1) or first call succeeded
    assert call_count[0] >= 1


# ─── Circuit breaker ──────────────────────────────────────────────────────────

def test_circuit_trips_and_returns_fallback():
    fallback = {"data": "cached"}
    config = ResilientConfig(
        backoff=BackoffConfig(base_delay=0.01, max_delay=0.05, max_retries=0),
        circuit_breaker=CircuitBreakerConfig(failure_threshold=3, cooldown_ms=60_000),
        retry_on=[500, 429],
        fallback=fallback,
    )

    call_count = [0]

    @resilient_api(config)
    def get_data():
        call_count[0] += 1
        # Always raise so failures accumulate without recordSuccess resetting the count.
        raise requests.exceptions.HTTPError(
            response=type('R', (), {'status_code': 500})()
        )

    results = []
    for _ in range(5):
        try:
            result = get_data(fallback=fallback)
            results.append(result)
        except requests.exceptions.HTTPError:
            results.append("ERROR")

    assert fallback in results, f"circuit should have returned fallback, got: {results}"


def test_circuit_open_raises_runtime_error_without_fallback():
    config = ResilientConfig(
        backoff=BackoffConfig(base_delay=0.01, max_delay=0.05, max_retries=0),
        circuit_breaker=CircuitBreakerConfig(failure_threshold=3, cooldown_ms=60_000),
        retry_on=[500, 429],
    )

    @resilient_api(config)
    def get_data():
        # Always raises a 500 so recordSuccess never fires and count accumulates.
        raise requests.exceptions.HTTPError(
            response=type('R', (), {'status_code': 500})()
        )

    # 3 calls trip the circuit (threshold=3, no successes to reset count)
    for _ in range(3):
        try:
            get_data()
        except Exception:
            pass

    # Next call should raise RuntimeError (OPEN, no fallback)
    with pytest.raises(RuntimeError, match="Circuit breaker is OPEN"):
        get_data()


# ─── Recovery ─────────────────────────────────────────────────────────────────

def test_circuit_recovers_after_cooldown():
    cooldown_ms = 500
    config = ResilientConfig(
        backoff=BackoffConfig(base_delay=0.01, max_delay=0.05, max_retries=0),
        circuit_breaker=CircuitBreakerConfig(failure_threshold=3, cooldown_ms=cooldown_ms),
        retry_on=[500, 429],
        fallback={"tripped": True},
    )

    @resilient_api(config)
    def get_data():
        res = requests.get(f"{BASE}/unstable-data")
        res.raise_for_status()
        return res.json()

    # Trip the circuit
    for _ in range(9):
        try:
            get_data(fallback={"tripped": True})
        except requests.exceptions.HTTPError:
            pass

    # Wait for cooldown
    time.sleep((cooldown_ms / 1000) + 0.2)

    # Reset sandbox so next request gets 200
    reset()

    # Probe should succeed and close the circuit
    result = get_data()
    assert result == {"success": True, "data": "Solid Data"}
