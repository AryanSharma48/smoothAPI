# @codingaryan/smoothapi

API resilience library for TypeScript/JavaScript. It wraps the native `fetch` API with **exponential backoff, full jitter, and a finite-state machine circuit breaker** to protect against cascading failures.

Zero dependencies. Small bundle size. Built for modern ESM.

## Install

```bash
npm install @codingaryan/smoothapi
```

## Features

- **Exponential Backoff with Full Jitter:** Prevents the "thundering herd" problem by randomizing retry delays.
- **Circuit Breaker (FSM):** Isolated per-domain state machine (`CLOSED` → `OPEN` → `HALF_OPEN`).
- **Smart Retries:** Automatically retries on specific HTTP status codes (e.g., 429, 500, 502, 503, 504) while throwing immediately on client errors (400, 401, 404).
- **Graceful Fallbacks:** Optionally serve cached or default data instantly when the circuit is `OPEN`.

## Usage

### Basic Usage (Defaults)

If you don't need custom configurations, you can instantiate the resilient fetch with its defaults by simply passing an empty object.

```typescript
import { createResilientFetch } from '@codingaryan/smoothapi';

// Create it with default settings
const fetchWithRetry = createResilientFetch({});

async function main() {
  try {
    // Drop-in replacement for native fetch
    const response = await fetchWithRetry('https://api.example.com/data');
    const data = await response.json();
    console.log(data);
  } catch (err) {
    console.error("Request failed completely:", err);
  }
}
```

**Default Settings provided automatically:**
- **Retries**: 3 attempts
- **Backoff Base Delay**: 100 milliseconds
- **Circuit Failure Threshold**: Trips after 3 consecutive failures
- **Circuit Cooldown**: Stays open for 10 seconds before probing
- **Status Codes to Retry**: `429`, `500`, `502`, `503`, and `504`

### Advanced Usage (Custom Settings)

You can override any of the defaults to suit your application's needs, such as adding a fallback object.

```typescript
import { createResilientFetch } from '@codingaryan/smoothapi';

const fetchWithRetry = createResilientFetch({
  backoff: {
    baseDelay: 100,      // ms to wait before first retry
    maxDelay: 30000,     // cap on exponential growth
    maxRetries: 3        // max number of retry attempts
  },
  circuitBreaker: {
    failureThreshold: 3, // trip OPEN after 3 consecutive failures
    cooldownMs: 10000    // stay OPEN for 10 seconds before probing
  },
  // Optional: Return this instead of throwing when the circuit is OPEN
  fallback: { error: "Service degraded, returning stale data." },
  // Optional: Custom status codes to retry on
  retryOn: [429, 500, 502, 503, 504]
});

async function main() {
  try {
    const response = await fetchWithRetry('https://api.example.com/data');
    
    // If fallback triggered, it returns your fallback object directly
    if ('error' in response) {
        console.log("Fallback triggered:", response.error);
        return;
    }
    
    // Otherwise it's a standard Response object
    const data = await response.json();
    console.log(data);
  } catch (err) {
    console.error("Request failed completely:", err);
  }
}
```

### Client Error Handling & Alerts

By default, client errors (e.g. `400`, `401`, `403`, `404`, `405`) resolve immediately and bypass the retry loop. If you want to handle these errors gracefully and alert users:

```typescript
import { createResilientFetch } from '@codingaryan/smoothapi';

const fetchWithRetry = createResilientFetch({
  fallbackOnNonRetryable: true,
  // Optional: Trigger custom UI logic when a client error happens
  onNonRetryableError: (status, message) => {
    console.log(`Custom callback: Received status ${status}`);
  },
  // Optional: Fallback returned on non-retryable errors
  fallback: { error: "Page not found." }
});
```

* **Default Alerting**: If `fallbackOnNonRetryable` is `true` and no custom `onNonRetryableError` is provided, running in a browser environment will trigger a standard `window.alert("Non-retryable HTTP error: [status]")`. In backend/Node environments, it logs the warning to `console.error`.
* **Graceful Return**: If no custom `fallback` is configured, it returns a mock `Response` wrapper with the status code and a JSON error body: `{ error: true, status: 404, message: "..." }`. Callers can safely call `.json()`, `.status`, or `.ok` on it without crashing.

## How It Works

1. **Host Extraction:** The domain is automatically extracted from the URL. The circuit breaker state is isolated per host (e.g., `api.github.com` failing won't trip the circuit for `api.stripe.com`).
2. **Circuit Check:** Before making a network request, the breaker checks the state. If it's `OPEN`, the request is blocked instantly (returning your fallback, or throwing a `CircuitOpenError`).
3. **Execution & Retries:** If the response status is in your `retryOn` list, it's counted as a failure and retried with backoff.
4. **Recovery:** After `cooldownMs`, the breaker enters `HALF_OPEN` state. The next request acts as a probe. If it succeeds, the circuit closes. If it fails, it snaps back to `OPEN` immediately.

## License

MIT
