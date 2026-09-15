import asyncio
import time
import pytest
import requests
from smooth_api import (
    CircuitStateChangeEvent,
    RetryContext,
    SmoothConfig,
    smooth_api,
)
from smooth_api.config import BackoffConfig, CircuitBreakerConfig

BASE = "http://localhost:3001"


def reset():
    try:
        requests.get(f"{BASE}/reset")
    except Exception:
        pass


@pytest.fixture(autouse=True)
def reset_counter():
    reset()


def test_on_retry_fires_with_correct_context_sync():
    reset()
    calls = []

    def on_retry(ctx: RetryContext):
        calls.append(ctx)

    config = SmoothConfig(
        backoff=BackoffConfig(max_retries=3, base_delay=0.01, max_delay=0.05),
        on_retry=on_retry,
    )

    @smooth_api(config)
    def call_fail():
        resp = requests.get(f"{BASE}/always-fail")
        resp.raise_for_status()
        return resp

    resp = call_fail()
    assert resp.status_code == 500
    assert len(calls) == 3, f"Expected 3 retry calls, got {len(calls)}"

    first = calls[0]
    assert first.attempt == 1
    assert first.max_retries == 3
    assert first.delay_ms >= 0
    assert first.delay >= 0
    assert first.status == 500
    assert "call_fail" in first.domain


@pytest.mark.asyncio
async def test_on_retry_fires_with_correct_context_async():
    reset()
    calls = []

    def on_retry(ctx: RetryContext):
        calls.append(ctx)

    config = SmoothConfig(
        backoff=BackoffConfig(max_retries=2, base_delay=0.01, max_delay=0.05),
        on_retry=on_retry,
    )

    @smooth_api(config)
    async def call_fail_async(url: str):
        resp = requests.get(url)
        resp.raise_for_status()
        return resp

    resp = await call_fail_async(f"{BASE}/always-fail")
    assert resp.status_code == 500
    assert len(calls) == 2

    first = calls[0]
    assert first.attempt == 1
    assert first.max_retries == 2
    assert first.delay_ms >= 0
    assert first.status == 500
    assert first.url == f"{BASE}/always-fail"


def test_on_circuit_state_change_transitions():
    reset()
    events: list[CircuitStateChangeEvent] = []

    def on_state_change(event: CircuitStateChangeEvent):
        events.append(event)

    config = SmoothConfig(
        backoff=BackoffConfig(max_retries=0, base_delay=0.01),
        circuit_breaker=CircuitBreakerConfig(failure_threshold=2, cooldown_ms=50),
        on_circuit_state_change=on_state_change,
        fallback="circuit_fallback",
    )

    @smooth_api(config)
    def unstable_call(succeed: bool = False):
        if not succeed:
            resp = requests.get(f"{BASE}/always-fail")
            resp.raise_for_status()
            return resp
        resp = requests.get(f"{BASE}/health")
        resp.raise_for_status()
        return resp

    # 1st failure -> no state change (failure_count = 1)
    unstable_call()
    assert len(events) == 0

    # 2nd failure -> exceeds threshold -> trips to OPEN
    unstable_call()
    assert len(events) == 1
    assert events[0].from_state == "CLOSED"
    assert events[0].to_state == "OPEN"
    assert events[0].to == "OPEN"
    assert events[0].failure_count == 2

    # Wait for cooldown to expire
    time.sleep(0.07)

    # 3rd attempt: Probes HALF_OPEN, but fails again -> back to OPEN
    unstable_call()
    assert len(events) == 3
    assert events[1].from_state == "OPEN"
    assert events[1].to_state == "HALF_OPEN"
    assert events[2].from_state == "HALF_OPEN"
    assert events[2].to_state == "OPEN"

    # Wait for cooldown to expire again
    time.sleep(0.07)
    reset()

    # 4th attempt: Probes HALF_OPEN and succeeds -> transitions to CLOSED
    res = unstable_call(succeed=True)
    assert res.status_code == 200
    assert len(events) == 5
    assert events[3].from_state == "OPEN"
    assert events[3].to_state == "HALF_OPEN"
    assert events[4].from_state == "HALF_OPEN"
    assert events[4].to_state == "CLOSED"
    assert events[4].failure_count == 0


def test_hook_exceptions_do_not_crash_pipeline():
    reset()
    retry_called = False
    state_change_called = False

    def buggy_on_retry(ctx):
        nonlocal retry_called
        retry_called = True
        raise RuntimeError("User bug in on_retry hook")

    def buggy_on_state_change(event):
        nonlocal state_change_called
        state_change_called = True
        raise RuntimeError("User bug in on_circuit_state_change hook")

    config = SmoothConfig(
        backoff=BackoffConfig(max_retries=1, base_delay=0.01),
        circuit_breaker=CircuitBreakerConfig(failure_threshold=1, cooldown_ms=1000),
        on_retry=buggy_on_retry,
        on_circuit_state_change=buggy_on_state_change,
    )

    @smooth_api(config)
    def call_fail():
        resp = requests.get(f"{BASE}/always-fail")
        resp.raise_for_status()
        return resp

    resp = call_fail()
    assert resp.status_code == 500
    assert retry_called is True
    assert state_change_called is True


@pytest.mark.asyncio
async def test_async_coroutine_hooks_support():
    reset()
    retry_async_called = False
    state_async_called = False

    async def async_on_retry(ctx: RetryContext):
        nonlocal retry_async_called
        await asyncio.sleep(0.001)
        retry_async_called = True

    async def async_on_state_change(event: CircuitStateChangeEvent):
        nonlocal state_async_called
        await asyncio.sleep(0.001)
        state_async_called = True

    config = SmoothConfig(
        backoff=BackoffConfig(max_retries=1, base_delay=0.01),
        circuit_breaker=CircuitBreakerConfig(failure_threshold=1, cooldown_ms=1000),
        on_retry=async_on_retry,
        on_circuit_state_change=async_on_state_change,
    )

    @smooth_api(config)
    async def call_fail():
        resp = requests.get(f"{BASE}/always-fail")
        resp.raise_for_status()
        return resp

    resp = await call_fail()
    assert resp.status_code == 500
    # Allow scheduled task to run
    await asyncio.sleep(0.05)
    assert retry_async_called is True
    assert state_async_called is True
