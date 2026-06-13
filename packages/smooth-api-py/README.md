# smooth-api (Python)

API resilience library for Python — exponential backoff with full jitter and a finite state machine circuit breaker. Mirrors the TypeScript package behaviour exactly.

## Install

```bash
pip install smooth-api
```

## Usage

```python
from smooth_api import resilient_api, ResilientConfig
from smooth_api.config import BackoffConfig, CircuitBreakerConfig

config = ResilientConfig(
    backoff=BackoffConfig(base_delay=0.1, max_delay=30.0, max_retries=3),
    circuit_breaker=CircuitBreakerConfig(failure_threshold=3, cooldown_ms=10_000),
    fallback={"data": "cached"},
)

@resilient_api(config)
def get_data():
    import requests
    res = requests.get("http://localhost:3001/unstable-data")
    res.raise_for_status()
    return res.json()

# runtime fallback override
result = get_data(fallback={"data": "override fallback"})
```

### Async functions

```python
@resilient_api(config)
async def get_data_async():
    import httpx
    async with httpx.AsyncClient() as client:
        res = await client.get("http://localhost:3001/unstable-data")
        res.raise_for_status()
        return res.json()
```

## Running tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## License

MIT
