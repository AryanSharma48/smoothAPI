import pytest
import requests
from smooth_api import resilient_api, ResilientConfig
from smooth_api.config import BackoffConfig, CircuitBreakerConfig

BASE = "http://localhost:3001"

@pytest.fixture(autouse=True)
def reset_counter():
    requests.get(f"{BASE}/reset")
    yield
    requests.get(f"{BASE}/reset")

def test_decorator_isolation_and_runtime_override():
    config = ResilientConfig(
        backoff=BackoffConfig(base_delay=0.01, max_delay=0.05, max_retries=0),
        circuit_breaker=CircuitBreakerConfig(failure_threshold=2, cooldown_ms=60_000),
        retry_on=[500],
        fallback={"default": True}
    )

    @resilient_api(config)
    def api_one():
        raise requests.exceptions.HTTPError(response=type('R', (), {'status_code': 500})())

    @resilient_api(config)
    def api_two():
        return {"success": True}

    # Trip api_one
    for _ in range(5):
        try:
            api_one()
        except requests.exceptions.HTTPError:
            pass

    # api_one should return fallback with override precedence
    res_one = api_one(fallback={"override": True})
    assert res_one == {"override": True}, "Runtime fallback override failed"

    # api_two should not be tripped
    res_two = api_two()
    assert res_two == {"success": True}, "Decorator state leaked to other decorated functions"
