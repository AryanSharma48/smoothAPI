# smoothapi-py

API resilience library for Python. It provides a decorator to wrap your HTTP requests with **exponential backoff, full jitter, and a finite-state machine circuit breaker** to protect against cascading failures.

Zero dependencies. Fully typed. Supports both sync and async functions out of the box. Automatically integrates with `requests` and `httpx` if installed.

## Install

```bash
pip install smoothapi-py
```

## Features

- **Exponential Backoff with Full Jitter:** Prevents the "thundering herd" problem by randomizing retry delays.
- **Circuit Breaker (FSM):** Isolated state machine (`CLOSED` → `OPEN` → `HALF_OPEN`) per decorated function. Thread-safe execution.
- **Smart Retries:** Automatically detects HTTP status codes from `requests` and `httpx` exceptions. Retries on transient codes (429, 500, 502, 503, 504) and re-raises client errors immediately.
- **Graceful Fallbacks:** Optionally return cached or default data instantly when the circuit is `OPEN`, bypassing network IO entirely.

## Usage

Define your configuration once and apply the `@resilient_api` decorator to your functions:

```python
from smooth_api import resilient_api, ResilientConfig
from smooth_api.config import BackoffConfig, CircuitBreakerConfig
import requests

config = ResilientConfig(
    backoff=BackoffConfig(
        base_delay=0.1,    # seconds to wait before first retry
        max_delay=30.0,    # cap on exponential growth
        max_retries=3      # max number of retry attempts
    ),
    circuit_breaker=CircuitBreakerConfig(
        failure_threshold=3, # trip OPEN after 3 consecutive failures
        cooldown_ms=10_000   # stay OPEN for 10 seconds before probing
    ),
    # Optional: return this exact object when the circuit is OPEN
    fallback={"status": "degraded", "data": []},
    # Optional: HTTP status codes to trigger a retry
    retry_on=[429, 500, 502, 503, 504]
)

@resilient_api(config)
def get_user_data(user_id: str):
    res = requests.get(f"https://api.example.com/users/{user_id}")
    res.raise_for_status()
    return res.json()

# Standard usage
try:
    data = get_user_data("123")
    print(data)
except Exception as e:
    print("Request failed completely:", e)

# You can also override the fallback at runtime per-call:
data = get_user_data("456", fallback={"status": "override"})
```

### Async Support

The decorator automatically detects if your function is a coroutine and uses `asyncio.sleep` instead of blocking the thread:

```python
import httpx

@resilient_api(config)
async def get_user_data_async(user_id: str):
    async with httpx.AsyncClient() as client:
        res = await client.get(f"https://api.example.com/users/{user_id}")
        res.raise_for_status()
        return res.json()
```

## How It Works

1. **Isolation:** The circuit breaker state is isolated per decorated function (`fn.__qualname__`).
2. **Circuit Check:** Before execution, the breaker checks the state. If it's `OPEN`, the request is blocked instantly (returning your fallback, or raising `RuntimeError`).
3. **Execution & Retries:** If an exception is raised, it attempts to extract the HTTP status code (supports `requests` and `httpx`). If the status is in `retry_on`, it's counted as a failure and the thread sleeps with backoff.
4. **Recovery:** After `cooldown_ms`, the breaker enters `HALF_OPEN`. The next execution acts as a probe. If it succeeds, the circuit closes. If it fails, it snaps back to `OPEN` immediately.

## License

MIT
