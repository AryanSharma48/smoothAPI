# smooth-api

> A zero-dependency, dual-language API Resilience and Fault-Tolerance Library.
> Implemented natively in **TypeScript** (NPM) and **Python** (PyPI).

---

## What it does

`smooth-api` wraps your HTTP calls with two battle-hardened resilience patterns:

1. **Exponential Backoff with Full Jitter** — automatically retries failed requests with randomized delays so clients don't hammer a recovering server in sync.
2. **Finite State Machine Circuit Breaker** — tracks failures per domain and trips a circuit to block further requests before they even hit the network, with automatic half-open probing for recovery.

---

## Workspace Layout

```
smooth-api/
├── packages/
│   ├── smooth-api-ts/          # TypeScript NPM package
│   └── smooth-api-py/          # Python PyPI package
├── sandbox/                    # Shared chaos test server (Express, port 3001)
├── README.md
└── .gitignore
```

---

## Quickstart

### TypeScript

```ts
import { createResilientFetch } from 'smooth-api';

const fetch = createResilientFetch({
  backoff: { baseDelay: 100, maxDelay: 5000, maxRetries: 3 },
  circuitBreaker: { failureThreshold: 3, cooldownMs: 10000 },
  fallback: { data: 'cached fallback' },
  retryOn: [429, 500, 502, 503, 504],
});

const res = await fetch('https://api.example.com/data');
```

### Python

```python
from smooth_api import resilient_api, ResilientConfig

config = ResilientConfig()

@resilient_api(config)
def get_data():
    import requests
    res = requests.get('https://api.example.com/data')
    res.raise_for_status()
    return res.json()

result = get_data(fallback={'data': 'cached fallback'})
```

---

## Running the Sandbox

```bash
cd sandbox
npm install
node server.js
# Listening on http://localhost:3001
```

---

## Running Tests

```bash
# TypeScript
cd packages/smooth-api-ts
npm install && npm run build && npm test

# Python
cd packages/smooth-api-py
pip install -e ".[dev]"
pytest tests/ -v
```

---

## License

MIT
