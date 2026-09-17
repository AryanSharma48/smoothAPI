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
- **Request Timeouts:** Configurable timeouts to automatically abort requests that hang indefinitely (async only).

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
    retry_on=[429, 500, 502, 503, 504],
    # Optional: Abort a request attempt if it takes longer than 5000ms (Async Only)
    timeout_ms=5000
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


### Async Support (httpx)

When building high-concurrency or non-blocking applications (such as FastAPI, Starlette, or `asyncio` workflows), blocking the main thread with synchronous HTTP libraries like `requests` degrades throughput. SmoothAPI natively supports asynchronous requests using [`httpx`](https://www.python-httpx.org/).

The `@smooth_api` decorator automatically detects coroutine functions (`async def`), executes non-blocking `asyncio.sleep` during backoff retry intervals, and enables async-only features such as [Request Deduplication](#request-deduplication-async-only) and `timeout_ms`.

#### Copy-Pasteable Example with `httpx.AsyncClient`

```python
import asyncio
import httpx
from smooth_api import smooth_api, SmoothConfig
from smooth_api.config import BackoffConfig, CircuitBreakerConfig

# 1. Configure SmoothAPI
config = SmoothConfig(
    backoff=BackoffConfig(
        base_delay=0.1,    # seconds before first retry
        max_delay=5.0,     # max backoff delay cap
        max_retries=3      # retry up to 3 times
    ),
    circuit_breaker=CircuitBreakerConfig(
        failure_threshold=3, # trip OPEN after 3 consecutive failures
        cooldown_ms=10_000   # stay OPEN for 10 seconds before probing
    ),
    retry_on=[429, 500, 502, 503, 504],
    timeout_ms=5000  # Abort if a request attempt hangs longer than 5000ms (Async Only)
)

# 2. Decorate your async function
@smooth_api(config)
async def get_user_data_async(client: httpx.AsyncClient, user_id: str):
    res = await client.get(f"https://api.example.com/users/{user_id}")
    res.raise_for_status()  # Always raise so SmoothAPI detects HTTP error codes
    return res.json()

# 3. Execute and properly await in an async context
async def main():
    async with httpx.AsyncClient() as client:
        try:
            data = await get_user_data_async(client, "123")
            print("Successfully retrieved data:", data)
        except Exception as e:
            print("Request failed after all retries or circuit opened:", e)

if __name__ == "__main__":
    asyncio.run(main())
```

**When to use Async vs. Sync:**
* **Use Async (`httpx.AsyncClient`)**: In async web frameworks (FastAPI, aiohttp, Starlette), microservices handling high I/O concurrency, or when using request deduplication or request timeouts (`timeout_ms`).
* **Use Sync (`requests`)**: In synchronous scripts, CLI tools, worker tasks (e.g. Celery sync workers), or simple linear pipelines without an active `asyncio` event loop.

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

### Lifecycle Event Hooks

SmoothAPI supports lifecycle event hooks to easily attach logging, metrics, alerting, or telemetry:

* **`on_retry`**: Invoked before sleeping on a retryable failure. Receives a `RetryContext` with attempt number, maximum retries, calculated delay (`delay` in seconds, `delay_ms` in milliseconds), HTTP status code (if available), error exception (if available), url, and function domain.
* **`on_circuit_state_change`**: Invoked whenever the circuit breaker transitions between states (`CLOSED`, `OPEN`, `HALF_OPEN`). Receives a `CircuitStateChangeEvent` with `domain`, `from_state`, `to_state`, and `failure_count`.

```python
from smooth_api import smooth_api, SmoothConfig, RetryContext, CircuitStateChangeEvent

def log_retry(ctx: RetryContext):
    print(f"[Retry] Attempt {ctx.attempt}/{ctx.max_retries} for {ctx.domain} (status: {ctx.status}). Retrying in {ctx.delay_ms:.0f}ms")

def log_circuit_transition(event: CircuitStateChangeEvent):
    print(f"[Circuit] {event.domain}: {event.from_state} -> {event.to_state} (failures: {event.failure_count})")

config = SmoothConfig(
    on_retry=log_retry,
    on_circuit_state_change=log_circuit_transition,
)
```

Both synchronous functions and `async def` coroutines are supported as hooks. All hooks execute with built-in fail-safe protection, ensuring that any exceptions raised inside user-defined callback functions never crash your request pipeline.

## How It Works

1. **Isolation:** The circuit breaker state is isolated per decorated function (`fn.__qualname__`).
2. **Circuit Check:** Before execution, the breaker checks the state. If it's `OPEN`, the request is blocked instantly (returning your fallback, or raising `RuntimeError`).
3. **Execution & Retries:** If an exception is raised, it attempts to extract the HTTP status code (supports `requests` and `httpx`). If the status is in `retry_on`, it's counted as a failure and the thread sleeps with backoff.
4. **Recovery:** After `cooldown_ms`, the breaker enters `HALF_OPEN`. The next execution acts as a probe. If it succeeds, the circuit closes. If it fails, it snaps back to `OPEN` immediately.
5. **Memory Management:** The circuit breaker cache is capped at 1,000 domains. When exceeded, `CLOSED` circuits with zero failures are swept to prevent memory leaks in dynamic environments.

## License

MIT
