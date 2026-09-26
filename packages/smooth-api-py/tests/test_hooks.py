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
    assert isinstance(first.error, Exception)
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
    assert isinstance(first.error, Exception)
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
    assert events[0].failureCount == 2

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


@pytest.mark.asyncio
async def test_async_hook_exceptions_do_not_crash_pipeline():
    reset()
    called = False

    async def buggy_async_hook(ctx):
        nonlocal called
        called = True
        raise RuntimeError("Bug in async hook")

    config = SmoothConfig(
        backoff=BackoffConfig(max_retries=1, base_delay=0.01),
        on_retry=buggy_async_hook,
    )

    @smooth_api(config)
    async def call_fail():
        resp = requests.get(f"{BASE}/always-fail")
        resp.raise_for_status()
        return resp

    resp = await call_fail()
    assert resp.status_code == 500
    await asyncio.sleep(0.02)
    assert called is True


def test_on_retry_extracts_url_from_class_method():
    reset()
    calls = []

    class ApiService:
        @smooth_api(SmoothConfig(backoff=BackoffConfig(max_retries=1, base_delay=0.01), on_retry=calls.append))
        def fetch(self, url: str):
            resp = requests.get(url)
            resp.raise_for_status()
            return resp

    service = ApiService()
    service.fetch(f"{BASE}/always-fail")
    assert len(calls) == 1
    assert calls[0].url == f"{BASE}/always-fail"


def test_on_success_sync_clean_200():
    reset()
    success_calls = []
    failure_calls = []

    config = SmoothConfig(
        on_success=success_calls.append,
        on_failure=failure_calls.append,
    )

    @smooth_api(config)
    def call_health():
        return requests.get(f"{BASE}/health")

    resp = call_health()
    assert resp.status_code == 200
    assert len(success_calls) == 1
    assert len(failure_calls) == 0

    ctx = success_calls[0]
    assert ctx.status == 200
    assert ctx.attempts == 1
    assert ctx.duration_ms >= 0
    assert ctx.duration >= 0
    assert "health" in ctx.url


@pytest.mark.asyncio
async def test_on_success_async_after_retries():
    reset()
    success_calls = []
    retry_calls = []

    config = SmoothConfig(
        backoff=BackoffConfig(max_retries=3, base_delay=0.01, max_delay=0.05),
        on_retry=retry_calls.append,
        on_success=success_calls.append,
    )

    # First 2 calls hit 200, 3rd hits 500 and retries to 4th (200)
    requests.get(f"{BASE}/unstable-data")
    requests.get(f"{BASE}/unstable-data")

    @smooth_api(config)
    async def call_unstable():
        resp = requests.get(f"{BASE}/unstable-data")
        resp.raise_for_status()
        return resp

    resp = await call_unstable()
    assert resp.status_code == 200
    assert len(retry_calls) == 1
    assert len(success_calls) == 1
    assert success_calls[0].attempts == 2


def test_on_failure_500_when_retries_exhausted():
    reset()
    success_calls = []
    failure_calls = []

    config = SmoothConfig(
        backoff=BackoffConfig(max_retries=2, base_delay=0.01, max_delay=0.05),
        on_success=success_calls.append,
        on_failure=failure_calls.append,
    )

    @smooth_api(config)
    def call_fail():
        resp = requests.get(f"{BASE}/always-fail")
        resp.raise_for_status()
        return resp

    resp = call_fail()
    assert resp.status_code == 500
    assert len(success_calls) == 0, "on_success must NOT fire for 500"
    assert len(failure_calls) == 1, "on_failure must fire for 500"

    ctx = failure_calls[0]
    assert ctx.status == 500
    assert ctx.attempts == 3  # attempt 0, 1, 2
    assert ctx.is_circuit_open is False
    assert ctx.duration_ms >= 0


def test_on_failure_circuit_open():
    reset()
    failure_calls = []

    config = SmoothConfig(
        backoff=BackoffConfig(max_retries=0, base_delay=0.01),
        circuit_breaker=CircuitBreakerConfig(failure_threshold=1, cooldown_ms=5000),
        on_failure=failure_calls.append,
    )

    @smooth_api(config)
    def call_fail():
        resp = requests.get(f"{BASE}/always-fail")
        resp.raise_for_status()
        return resp

    # 1st call trips breaker
    call_fail()
    assert len(failure_calls) == 1

    # 2nd call blocked by OPEN circuit
    with pytest.raises(RuntimeError, match="Circuit breaker is OPEN"):
        call_fail()

    assert len(failure_calls) == 2
    second_ctx = failure_calls[1]
    assert second_ctx.is_circuit_open is True
    assert second_ctx.isCircuitOpen is True
    assert second_ctx.attempts == 0


def test_on_success_and_failure_exceptions_safe():
    reset()

    def buggy_success(ctx):
        raise ValueError("Bug in on_success")

    def buggy_failure(ctx):
        raise ValueError("Bug in on_failure")

    config = SmoothConfig(
        backoff=BackoffConfig(max_retries=0, base_delay=0.01),
        on_success=buggy_success,
        on_failure=buggy_failure,
    )

    @smooth_api(config)
    def call_health():
        return requests.get(f"{BASE}/health")

    @smooth_api(config)
    def call_fail():
        resp = requests.get(f"{BASE}/always-fail")
        resp.raise_for_status()
        return resp

    # Should not crash on success hook bug
    res = call_health()
    assert res.status_code == 200

    # Should not crash on failure hook bug
    fail_res = call_fail()
    assert fail_res.status_code == 500


def test_camel_case_hook_aliases():
    reset()
    success_calls = []
    failure_calls = []

    config = SmoothConfig(
        backoff=BackoffConfig(max_retries=0, base_delay=0.01),
        onSuccess=success_calls.append,
        onFailure=failure_calls.append,
    )

    @smooth_api(config)
    def call_health():
        return requests.get(f"{BASE}/health")

    @smooth_api(config)
    def call_fail():
        resp = requests.get(f"{BASE}/always-fail")
        resp.raise_for_status()
        return resp

    call_health()
    assert len(success_calls) == 1

    call_fail()
    assert len(failure_calls) == 1

