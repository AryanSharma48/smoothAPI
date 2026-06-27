# smoothapi-py

API protection library for Python. It provides a decorator to wrap your HTTP requests with **exponential backoff, full jitter, and a finite-state machine circuit breaker** to protect against cascading failures.

Zero dependencies. Fully typed. Supports both sync and async functions out of the box. Automatically integrates with `requests` and `httpx` if installed.

## Install

```bash
pip install smoothapi-py
```

## Features

- **Exponential Backoff with Full Jitter:** Prevents the "thundering herd" problem by randomizing retry delays.
- **Circuit Breaker (FSM):** Isolated state machine (`CLOSED` → `OPEN` → `HALF_OPEN`) per decorated function. Thread-safe execution.
- **Smart Retries:** Automatically detects HTTP status codes from `requests` and `httpx` exceptions. Retries on retryable codes (429, 500, 502, 503, 504) and re-raises client errors immediately.
- **Graceful Fallbacks:** Optionally return cached or default data instantly when the circuit is `OPEN`, bypassing network IO entirely.
- **Request Deduplication:** Automatically merges concurrent identical requests into a single network call (async only).

## Usage

### Basic Usage (Defaults)

If you don't need custom configurations, you can use the decorator with its defaults by passing an empty config object.

```python
import requests
from smooth_api import smooth_api, SmoothConfig

# Create it with default settings
config = SmoothConfig()

@smooth_api(config)
def get_user_data(user_id: str):
    res = requests.get(f"https://api.example.com/users/{user_id}")
    res.raise_for_status() # Always raise so the decorator knows it failed!
    return res.json()

# Standard usage
try:
    data = get_user_data("123")
    print(data)
except Exception as e:
    print("Request failed completely:", e)
```

**Default Settings provided automatically:**
- **Retries**: 3 attempts
- **Backoff Base Delay**: 0.1 seconds (100 milliseconds)
- **Circuit Failure Threshold**: Trips after 3 consecutive failures
- **Circuit Cooldown**: Stays open for 10 seconds before probing
- **Status Codes to Retry**: `429`, `500`, `502`, `503`, and `504`

### Advanced Usage (Custom Settings)

You can override any of the defaults to suit your application's needs, such as adding a fallback object.

```python
from smooth_api import smooth_api, SmoothConfig
from smooth_api.config import BackoffConfig, CircuitBreakerConfig
import requests

config = SmoothConfig(
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

@smooth_api(config)
def get_user_data(user_id: str):
    res = requests.get(f"https://api.example.com/users/{user_id}")
    res.raise_for_status()
    return res.json()

# You can also override the fallback at runtime per-call:
data = get_user_data("456", fallback={"status": "override"})
```

### Client Error Handling & Warnings

By default, non-retryable client errors (e.g. `400`, `401`, `403`, `404`, `405`) bubble up and raise exceptions immediately. If you want to intercept these client errors:

```python
from smooth_api import smooth_api, SmoothConfig

def my_callback(status: int, message: str):
    print(f"Error hook: Received client error {status}")

config = SmoothConfig(
    fallback_on_non_retryable=True,
    # Optional: Custom error hook function
    on_non_retryable_error=my_callback,
    # Optional: Fallback returned on non-retryable errors
    fallback={"status": "error", "message": "Not Found"}
)
```

* **Default Warning**: If `fallback_on_non_retryable` is `True` and no custom `on_non_retryable_error` is defined, it will write a warning message to `sys.stderr`.
* **Graceful Return**: If no `fallback` is configured, it returns a mock `Response` wrapper with `status_code`, `.json()` returning `{"error": True, "status": status, "message": "..."}`, and `.ok` returning `False`. Code downstream can check `res.status_code` or call `res.json()` without raising exceptions.


### Async Support

The decorator automatically detects if your function is a coroutine and uses `asyncio.sleep` instead of blocking the thread:

```python
import httpx

@smooth_api(config)
async def get_user_data_async(user_id: str):
    async with httpx.AsyncClient() as client:
        res = await client.get(f"https://api.example.com/users/{user_id}")
        res.raise_for_status()
        return res.json()
```

### Request Deduplication (Async Only)

When multiple identical async requests are made concurrently, SmoothAPI can execute only one network call and share the result with all callers. This reduces unnecessary load on downstream services.

**Enable with default key function** (deduplicates by positional args):

```python
import httpx
from smooth_api import smooth_api, SmoothConfig
from smooth_api.config import DeduplicationConfig

config = SmoothConfig(deduplication=DeduplicationConfig())

@smooth_api(config)
async def get_user(user_id: int):
    async with httpx.AsyncClient() as client:
        res = await client.get(f"https://api.example.com/users/{user_id}")
        res.raise_for_status()
        return res.json()

# All three calls share a single network request
import asyncio
results = await asyncio.gather(
    get_user(1),
    get_user(1),
    get_user(1),
)
```

**Custom key function** for advanced coalescing:

```python
from smooth_api.config import DeduplicationConfig

def my_key(*args, **kwargs):
    # Deduplicate by second argument (resource type)
    return str(args[1]) if len(args) > 1 else str(args[0])

config = SmoothConfig(deduplication=DeduplicationConfig(key_fn=my_key))
```

**Opt out of deduplication** for specific calls:

```python
config = SmoothConfig(
    deduplication=DeduplicationConfig(
        key_fn=lambda *a, **k: None  # Return None to skip dedup
    )
)
```

* **Default Behavior**: Deduplicates by joining positional args with `:`. E.g., `get_user(1)` produces key `"1"`.
* **Error Propagation**: If the coroutine raises an exception, all waiting callers receive the same exception.
* **Settlement**: Once a call completes, the next call with the same key triggers a fresh execution.
* **Sync Functions**: Deduplication only works with async-decorated functions. Sync functions are unaffected.

## How It Works

1. **Isolation:** The circuit breaker state is isolated per decorated function (`fn.__qualname__`).
2. **Circuit Check:** Before execution, the breaker checks the state. If it's `OPEN`, the request is blocked instantly (returning your fallback, or raising `RuntimeError`).
3. **Execution & Retries:** If an exception is raised, it attempts to extract the HTTP status code (supports `requests` and `httpx`). If the status is in `retry_on`, it's counted as a failure and the thread sleeps with backoff.
4. **Recovery:** After `cooldown_ms`, the breaker enters `HALF_OPEN`. The next execution acts as a probe. If it succeeds, the circuit closes. If it fails, it snaps back to `OPEN` immediately.

## License

MIT
