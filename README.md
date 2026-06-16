<p align="center">
  <img src="public/logo.svg" alt="SmoothAPI logo" width="650" />
</p>

<p align="center">
  <a href="https://github.com/AryanSharma48/smoothAPI/actions"><img src="https://img.shields.io/github/actions/workflow/status/AryanSharma48/smoothAPI/ci.yml?branch=main&style=flat-square&label=CI&color=3b82f6" alt="CI Status"></a>
  <a href="https://www.npmjs.com/package/@codingaryan/smoothapi"><img src="https://img.shields.io/npm/v/@codingaryan/smoothapi?style=flat-square&color=8b5cf6" alt="NPM Version"></a>
  <a href="https://pypi.org/project/smoothapi-py/"><img src="https://img.shields.io/pypi/v/smoothapi-py?style=flat-square&color=ec4899" alt="PyPI Version"></a>
  <a href="https://www.npmjs.com/package/@codingaryan/smoothapi"><img src="https://img.shields.io/npm/dm/@codingaryan/smoothapi?style=flat-square&color=10b981" alt="NPM Downloads"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/AryanSharma48/smoothAPI?style=flat-square&color=6b7280" alt="License"></a>
</p>

A failing third-party API can bring down your entire application, leading to cascading service failures, degraded user experience, and lost revenue. How do you protect your systems and keep them resilient, even when downstream dependencies are completely unresponsive or failing?

Enter **SmoothAPI**. SmoothAPI stops third-party API crashes from breaking your app. It wraps your HTTP calls with industry-standard resilience patterns, catches network errors instantly, spaces out retries so recovering servers can breathe, and serves safe backup data the millisecond a service goes completely dead.

A zero-dependency, dual-language API resilience and fault-tolerance library, implemented natively in **TypeScript** (`@codingaryan/smoothapi` on NPM) and **Python** (`smoothapi-py` on PyPI).

---

## What it does

`SmoothAPI` wraps your HTTP calls with two resilience patterns:

1. **Exponential Backoff with Full Jitter** — automatically retries failed requests with randomized delays so clients don't hammer a recovering server in sync.
2. **Finite State Machine Circuit Breaker** — tracks failures per domain and trips a circuit to block further requests before they even hit the network, with automatic half-open probing for recovery.

### Features
- **Zero Dependencies:** Keeps your bundle and environment clean.
- **Dual Language Support:** Native implementations for both TypeScript/JavaScript and Python.
- **Sync & Async Support (Python):** Seamlessly works with `asyncio`, `requests`, and `httpx`.
- **Graceful Fallbacks:** Return default or cached data instantly when the circuit is open, bypassing network IO entirely.
- **Smart Retries:** Automatically detect HTTP status codes to retry on transient errors (e.g., 429, 500, 502, 503, 504).

---

## Workspace Layout

```
smooth-api/
├── packages/
│   ├── smooth-api-ts/          # TypeScript NPM package (@codingaryan/smoothapi)
│   └── smooth-api-py/          # Python PyPI package (smoothapi-py)
├── sandbox/                    # Shared chaos test server (Express, port 3001)
├── README.md
└── .gitignore
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
import { createResilientFetch } from '@codingaryan/smoothapi';

const fetch = createResilientFetch({});

const res = await fetch('https://api.example.com/data');
```

**Advanced Usage (Custom):**
```ts
import { createResilientFetch } from '@codingaryan/smoothapi';

const fetch = createResilientFetch({
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
from smooth_api import resilient_api, ResilientConfig
import requests

config = ResilientConfig()

@resilient_api(config)
def get_data():
    res = requests.get('https://api.example.com/data')
    res.raise_for_status()
    return res.json()
```

**Advanced Usage (Custom):**
```python
from smooth_api import resilient_api, ResilientConfig
import requests

config = ResilientConfig(
    backoff={"base_delay": 0.1, "max_delay": 30.0, "max_retries": 3},
    circuit_breaker={"failure_threshold": 3, "cooldown_ms": 10000},
    fallback={'data': 'cached fallback'},
    retry_on=[429, 500, 502, 503, 504]
)

@resilient_api(config)
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

## Running the Sandbox

The sandbox provides an Express server with chaotic endpoints to test resilience.

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

## License

MIT
