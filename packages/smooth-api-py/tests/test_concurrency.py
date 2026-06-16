import asyncio
import pytest
import httpx
from smooth_api import resilient_api, ResilientConfig
from smooth_api.config import BackoffConfig, CircuitBreakerConfig

BASE = "http://localhost:3001"

@pytest.fixture(autouse=True)
def reset_counter():
    import requests
    requests.get(f"{BASE}/reset")
    yield
    requests.get(f"{BASE}/reset")

@pytest.mark.asyncio
async def test_async_wrapper_concurrency():
    config = ResilientConfig(
        backoff=BackoffConfig(base_delay=0.01, max_delay=0.05, max_retries=0),
        circuit_breaker=CircuitBreakerConfig(failure_threshold=3, cooldown_ms=60_000),
        retry_on=[500],
        fallback={"tripped": True}
    )

    @resilient_api(config)
    async def get_data():
        request = httpx.Request("GET", f"{BASE}/unstable-data")
        response = httpx.Response(500, request=request)
        raise httpx.HTTPStatusError("error", request=request, response=response)

    # Trip the circuit with 8 concurrent requests
    tasks = [get_data() for _ in range(8)]
    await asyncio.gather(*tasks, return_exceptions=True)

    # Now the circuit should be open, so the next request should instantly return fallback
    fallback = await get_data()
    assert fallback == {"tripped": True}, "Circuit should have tripped under load and returned fallback"
