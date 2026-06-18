"""
Tests for the Request Deduplication feature (Python package).

All tests are fully self-contained — no sandbox server required.
"""
from __future__ import annotations

import asyncio
import time
import pytest

from smooth_api import resilient_api, ResilientConfig, DeduplicationConfig
from smooth_api.config import BackoffConfig, CircuitBreakerConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fast_config(**extra) -> ResilientConfig:
    """Minimal config: no real delays, no retries."""
    return ResilientConfig(
        backoff=BackoffConfig(base_delay=0, max_delay=0, max_retries=0),
        circuit_breaker=CircuitBreakerConfig(failure_threshold=100, cooldown_ms=60_000),
        **extra,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deduplication_disabled_by_default():
    """Without deduplication config each call runs the function independently."""
    counter = {"calls": 0}

    @resilient_api(_fast_config())
    async def fetch_user(user_id: int):
        counter["calls"] += 1
        await asyncio.sleep(0.02)  # simulate latency
        return {"id": user_id}

    results = await asyncio.gather(*[fetch_user(1) for _ in range(3)])

    assert counter["calls"] == 3, "Expected 3 independent calls (dedup off)"
    for r in results:
        assert r == {"id": 1}


@pytest.mark.asyncio
async def test_concurrent_identical_calls_deduplicated():
    """3 concurrent calls with the same arg produce exactly 1 execution."""
    counter = {"calls": 0}

    @resilient_api(_fast_config(deduplication=DeduplicationConfig()))
    async def fetch_user(user_id: int):
        counter["calls"] += 1
        await asyncio.sleep(0.02)
        return {"id": user_id}

    results = await asyncio.gather(*[fetch_user(1) for _ in range(3)])

    assert counter["calls"] == 1, "Expected exactly 1 network call for 3 concurrent identical requests"
    for r in results:
        assert r == {"id": 1}


@pytest.mark.asyncio
async def test_different_args_not_deduplicated():
    """Calls with different arguments must each execute independently."""
    counter = {"calls": 0}

    @resilient_api(_fast_config(deduplication=DeduplicationConfig()))
    async def fetch_user(user_id: int):
        counter["calls"] += 1
        await asyncio.sleep(0.02)
        return {"id": user_id}

    results = await asyncio.gather(fetch_user(1), fetch_user(2))

    assert counter["calls"] == 2, "Different keys → no deduplication"
    assert results[0] == {"id": 1}
    assert results[1] == {"id": 2}


@pytest.mark.asyncio
async def test_sequential_calls_not_deduplicated():
    """After a call settles the next sequential call triggers a fresh execution."""
    counter = {"calls": 0}

    @resilient_api(_fast_config(deduplication=DeduplicationConfig()))
    async def fetch_user(user_id: int):
        counter["calls"] += 1
        return {"id": user_id}

    await fetch_user(1)
    await fetch_user(1)

    assert counter["calls"] == 2, "Sequential calls must each hit the function"


@pytest.mark.asyncio
async def test_error_propagated_to_all_callers():
    """When the executing coroutine raises, all waiting callers get the same exception."""
    counter = {"calls": 0}

    @resilient_api(_fast_config(deduplication=DeduplicationConfig()))
    async def fetch_user(user_id: int):
        counter["calls"] += 1
        await asyncio.sleep(0.01)
        raise ValueError("upstream failure")

    results = await asyncio.gather(
        *[fetch_user(1) for _ in range(3)],
        return_exceptions=True,
    )

    assert counter["calls"] == 1, "Error path: still only one real call"
    for r in results:
        assert isinstance(r, ValueError), f"Expected ValueError, got {r!r}"
        assert "upstream failure" in str(r)


@pytest.mark.asyncio
async def test_custom_key_fn_coalesces_by_resource_type():
    """Custom key_fn allows arbitrary coalescing logic — here keyed on resource_type."""
    counter = {"calls": 0}

    # Key on the *second* argument (resource type), ignoring the ID.
    def resource_key(*args, **kwargs):
        return str(args[1]) if len(args) > 1 else str(args[0])

    @resilient_api(_fast_config(deduplication=DeduplicationConfig(key_fn=resource_key)))
    async def fetch_resource(resource_id: int, resource_type: str):
        counter["calls"] += 1
        await asyncio.sleep(0.02)
        return {"type": resource_type, "id": resource_id}

    # Two calls with different IDs but the same type → same key → deduplicated.
    results = await asyncio.gather(
        fetch_resource(1, "post"),
        fetch_resource(2, "post"),
    )

    assert counter["calls"] == 1, "Same resource_type → one call via custom key_fn"


@pytest.mark.asyncio
async def test_none_key_fn_opts_out_of_deduplication():
    """When key_fn returns None the call bypasses deduplication entirely."""
    counter = {"calls": 0}

    # Always return None → every call bypasses dedup.
    @resilient_api(_fast_config(deduplication=DeduplicationConfig(key_fn=lambda *a, **k: None)))
    async def fetch_user(user_id: int):
        counter["calls"] += 1
        await asyncio.sleep(0.02)
        return {"id": user_id}

    await asyncio.gather(*[fetch_user(1) for _ in range(3)])

    assert counter["calls"] == 3, "None key → every call executes the function"


# ---------------------------------------------------------------------------
# Benchmark (informational — does not fail the suite)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deduplication_benchmark(capsys):
    """Measures the overhead of the deduplication path vs plain calls."""
    CONCURRENCY = 200
    RUNS = 5

    @resilient_api(_fast_config())
    async def plain_fn(x: int):
        return x

    @resilient_api(_fast_config(deduplication=DeduplicationConfig()))
    async def deduped_fn(x: int):
        return x

    # Warm up
    await plain_fn(0)
    await deduped_fn(0)

    total_plain = 0.0
    for _ in range(RUNS):
        t0 = time.perf_counter()
        await asyncio.gather(*[plain_fn(i) for i in range(CONCURRENCY)])
        total_plain += time.perf_counter() - t0

    total_deduped = 0.0
    for _ in range(RUNS):
        t0 = time.perf_counter()
        await asyncio.gather(*[deduped_fn(i) for i in range(CONCURRENCY)])
        total_deduped += time.perf_counter() - t0

    avg_plain = total_plain / RUNS * 1000
    avg_deduped = total_deduped / RUNS * 1000

    with capsys.disabled():
        print(
            f"\n[Benchmark] {CONCURRENCY} concurrent requests × {RUNS} runs | "
            f"plain avg: {avg_plain:.2f}ms | deduped avg: {avg_deduped:.2f}ms"
        )
    # Benchmark is informational only — no timing assertion to avoid
    # flaky failures across machines and CI runners.
