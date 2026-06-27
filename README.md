<p align="center">
  <a href="https://smoothapi.org"><img src="public/logo.svg" alt="SmoothAPI logo" width="650" />
</p>

<p align="center">
  <a href="https://github.com/AryanSharma48/smoothAPI/actions"><img src="https://img.shields.io/github/actions/workflow/status/AryanSharma48/smoothAPI/ci.yml?branch=main&style=flat-square&label=CI&color=3b82f6" alt="CI Status"></a>
  <a href="https://www.npmjs.com/package/@codingaryan/smoothapi"><img src="https://img.shields.io/npm/v/@codingaryan/smoothapi?style=flat-square&color=8b5cf6" alt="NPM Version"></a>
  <a href="https://pypi.org/project/smoothapi-py/"><img src="https://img.shields.io/pypi/v/smoothapi-py?style=flat-square&color=ec4899" alt="PyPI Version"></a>
  <a href="https://www.npmjs.com/package/@codingaryan/smoothapi"><img src="https://img.shields.io/npm/dm/@codingaryan/smoothapi?style=flat-square&color=10b981" alt="NPM Downloads"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-6b7280?style=flat-square" alt="License"></a>
</p>

A failing third-party API can bring down your entire application, leading to cascading service failures, degraded user experience, and lost revenue. How do you protect your systems and keep them shielded, even when downstream dependencies are completely unresponsive or failing?

Enter **SmoothAPI**. SmoothAPI stops third-party API crashes from breaking your app. It wraps your HTTP calls with secure patterns, catches network errors instantly, spaces out retries so recovering servers can breathe, and serves safe backup data the millisecond a service goes completely dead.

A zero-dependency, dual-language API shielding and fault-tolerance library, implemented natively in **TypeScript** (`@codingaryan/smoothapi` on NPM) and **Python** (`smoothapi-py` on PyPI).

---

## What it does

`SmoothAPI` wraps your HTTP calls with two patterns:

1. **Exponential Backoff with Full Jitter** — automatically retries failed requests with randomized delays so clients don't hammer a recovering server.
2. **Finite State Machine Circuit Breaker** — tracks failures per domain and trips a circuit to block further requests before they even hit the network, with automatic half-open probing for recovery.

### Features
- **Zero Dependencies:** Keeps your bundle and environment clean.
- **Dual Language Support:** Native implementations for both TypeScript/JavaScript and Python.
- **Sync & Async Support (Python):** Seamlessly works with `asyncio`, `requests`, and `httpx`.
- **Graceful Fallbacks:** Return default or cached data instantly when the circuit is open, bypassing network IO entirely.
- **Smart Retries:** Automatically detect HTTP status codes to retry on transient errors (e.g., 429, 500, 502, 503, 504).
- **Request Deduplication** Automatically detect multiple requests for same external API, merging them into one and saving compute.
 
---

## Workspace Layout

```
smooth-api/
├── examples/                   # Browser examples showing the usade of SmoothAPI
├── packages/
│   ├── smooth-api-ts/          # TypeScript NPM package (@codingaryan/smoothapi)
│   └── smooth-api-py/          # Python PyPI package (smoothapi-py)
├── sandbox/                    # Shared chaos test server (Express, port 3001)
├── website/                    # Documentation website for SmoothAPI
├── README.md
├── CONTRIBUTING.md
└── .gitignore
```

### Flow Overview

```mermaid
sequenceDiagram
    participant Client
    participant SmoothAPI
    participant Target API

    Client->>SmoothAPI: 1. Request Data
    SmoothAPI->>Target API: 2. Fetch (Retries on Error)
    Target API-->>SmoothAPI: 3. Return Response
    SmoothAPI-->>Client: 4. Return Data or Fallback
```

---

## Quickstart

### TypeScript

> **Read the full documentation:** [TypeScript Package README](./packages/smooth-api-ts/README.md)

**Install:**
```bash
npm install @codingaryan/smoothapi
```

**Basic Usage (Defaults):**
```ts
import { createSmoothFetch } from '@codingaryan/smoothapi';

const fetch = createSmoothFetch({});

const res = await fetch('https://api.example.com/data');
```

**Advanced Usage (Custom):**
```ts
import { createSmoothFetch } from '@codingaryan/smoothapi';

const fetch = createSmoothFetch({
  backoff: { baseDelay: 100, maxDelay: 5000, maxRetries: 3 },
  circuitBreaker: { failureThreshold: 3, cooldownMs: 10000 },
  fallback: { data: 'cached fallback' },
  retryOn: [429, 500, 502, 503, 504],
});

const res = await fetch('https://api.example.com/data');
```

### Python

> **Read the full documentation:** [Python Package README](./packages/smooth-api-py/README.md)

**Install:**
```bash
pip install smoothapi-py
```

**Basic Usage (Defaults):**
```python
from smooth_api import smooth_api, SmoothConfig
import requests

config = SmoothConfig()

@smooth_api(config)
def get_data():
    res = requests.get('https://api.example.com/data')
    res.raise_for_status()
    return res.json()
```

**Advanced Usage (Custom):**
```python
from smooth_api import smooth_api, SmoothConfig
import requests

config = SmoothConfig(
    backoff={"base_delay": 0.1, "max_delay": 30.0, "max_retries": 3},
    circuit_breaker={"failure_threshold": 3, "cooldown_ms": 10000},
    fallback={'data': 'cached fallback'},
    retry_on=[429, 500, 502, 503, 504]
)

@smooth_api(config)
def get_data():
    res = requests.get('https://api.example.com/data')
    res.raise_for_status()
    return res.json()

# You can also override fallbacks at runtime per-call:
result = get_data(fallback={'data': 'dynamic override fallback'})
```

**Default Settings provided automatically:**
- **Retries**: 3 attempts
- **Backoff Base Delay**: 100 milliseconds
- **Circuit Failure Threshold**: Trips after 3 consecutive failures
- **Circuit Cooldown**: Stays open for 10 seconds before probing
- **Status Codes to Retry**: `429`, `500`, `502`, `503`, and `504`

*Note: The Python package fully supports async functions and `httpx` out of the box.*

---

## Client Error Handling & Graceful Fallbacks

By default, client errors (status codes `400` to `499` not in `retryOn` / `retry_on`) immediately fail and bypass retries. You can handle them gracefully using `fallbackOnNonRetryable` (TS) or `fallback_on_non_retryable` (Python):

* **TypeScript:**
  ```ts
  const fetch = createSmoothFetch({
    fallbackOnNonRetryable: true,
    // Optional custom callback (replaces default window.alert/console.error)
    onNonRetryableError: (status, message) => console.warn(message),
    // Optional fallback (otherwise returns a mock Response wrapper)
    fallback: { error: 'stale data' }
  });
  ```
  *If `fallbackOnNonRetryable` is `true` in a browser and no custom callback is set, it triggers a browser `alert()` popup by default.*

* **Python:**
  ```python
  config = SmoothConfig(
      fallback_on_non_retryable=True,
      # Optional custom callback (replaces default stderr warning)
      on_non_retryable_error=lambda status, msg: print(msg),
      # Optional fallback (otherwise returns a MockResponse wrapper)
      fallback={'error': 'stale data'}
  )
  ```
  *If `fallback_on_non_retryable` is `True` and no custom callback is set, it prints a warning to `sys.stderr` by default.*

---

## Running the Sandbox

The sandbox provides an Express server with chaotic endpoints to test protection using SmoothAPI.

```bash
cd sandbox
npm install
node server.js
# Listening on http://localhost:3001
```

---

## Running Tests

### TypeScript
```bash
cd packages/smooth-api-ts
npm install
npm run build
npm test
```

### Python
```bash
cd packages/smooth-api-py
pip install -e ".[dev]"
pytest tests/ -v
```

---

## Roadmap

### Core Reliability
- [ ] Request timeout support
- [ ] AbortController integration
- [ ] Retry-After header support
- [ ] Custom retry strategies

### Observability
- [ ] Event hooks
- [ ] Metrics hooks
- [ ] OpenTelemetry integration
- [ ] Structured logging support

### Ecosystem
- [x] Next.js example project
- [x] Express integration examples
- [x] Browser examples
- [ ] Benchmark suite

### Advanced Security and Performance
- [x] Request deduplication
- [ ] Redis-backed circuit breaker state
- [ ] Bulkhead pattern support
- [ ] Service health scoring
- [ ] Go engine for high concurrency and bare metal execution

---

## Contributing

Contributions are welcome! Join our [Discord Server](https://discord.gg/2NabXnQzmv) to connect with the maintainers and other contributors.

Whether it's fixing bugs, improving documentation, adding examples, or implementing new features, every contribution helps improve SmoothAPI.

Before opening a pull request, please read the contribution guidelines in [CONTRIBUTING.md](./CONTRIBUTING.md).

If you're looking to get started, check out issues labeled `good first issue` or `help wanted`.

---

## License

MIT

