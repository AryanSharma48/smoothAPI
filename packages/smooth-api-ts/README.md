# @codingaryan/smoothapi

API protection library for TypeScript/JavaScript. It wraps the native `fetch` API with state of the art protections like **exponential backoff, full jitter, and a finite-state machine circuit breaker** to protect against cascading failures.

Zero dependencies. Small bundle size. Built for modern ESM.

## Install

```bash
npm install @codingaryan/smoothapi
```

## Features

- **Exponential Backoff with Configurable Jitter:** Prevents the "thundering herd" problem by randomizing retry delays using `full`, `equal`, `decorrelated`, or `none` strategies.
- **Circuit Breaker (FSM):** Isolated per-domain state machine (`CLOSED` → `OPEN` → `HALF_OPEN`).
- **Smart Retries:** Automatically retries on specific HTTP status codes (e.g., 429, 500, 502, 503, 504) while throwing immediately on client errors (400, 401, 404).
- **Graceful Fallbacks:** Optionally serve cached or default data instantly when the circuit is `OPEN`.
- **Request Deduplication:** Automatically couples concurrent identical requests into a single network call.
- **Request Timeouts:** Configurable timeouts to automatically abort requests that hang indefinitely.
- **Lifecycle Event Hooks:** Listen to retry attempts and circuit state transitions for logging or telemetry.

## Usage

### Basic Usage (Defaults)

If you don't need custom configurations, you can use the smooth fetch with its defaults by simply passing an empty object.

```typescript
import { createSmoothFetch } from '@codingaryan/smoothapi';

// Create it with default settings
const fetchWithRetry = createSmoothFetch({});

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
- **Jitter Strategy**: `equal`
- **Circuit Failure Threshold**: Trips after 3 consecutive failures
- **Circuit Cooldown**: Stays open for 10 seconds before probing
- **Status Codes to Retry**: `429`, `500`, `502`, `503`, and `504`

### Advanced Usage (Custom Settings)

You can override any of the defaults to suit your application's needs, such as adding a fallback object.

```typescript
import { createSmoothFetch } from '@codingaryan/smoothapi';

const fetchWithRetry = createSmoothFetch({
  backoff: {
    baseDelay: 100,      // ms to wait before first retry
    maxDelay: 30000,     // cap on exponential growth
    maxRetries: 3        // max number of retry attempts
    jitter: 'equal',     // 'equal' (default) | 'full' | 'decorrelated' | 'none'
  },
  circuitBreaker: {
    failureThreshold: 3, // trip OPEN after 3 consecutive failures
    cooldownMs: 10000    // stay OPEN for 10 seconds before probing
  },
  // Optional: Return this instead of throwing when the circuit is OPEN
  fallback: { error: "Service degraded, returning stale data." },
  // Optional: Custom status codes to retry on
  retryOn: [429, 500, 502, 503, 504],
  // Optional: Abort a request attempt if it takes longer than 5000ms
  timeoutMs: 5000
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

### Jitter Strategies

To prevent the "thundering herd" problem, SmoothAPI applies randomized jitter to the exponential backoff delay. You can choose from four strategies via `backoff.jitter`:

- **`equal`** (default): `half + random(0, half)`. Guarantees at least half the capped delay, with some randomness.
- **`full`**: `random(0, capped)`. Maximum randomness, delay can be anywhere from 0 to the capped value.
- **`none`**: Deterministic exponential delay (`baseDelay * 2^attempt`, capped at `maxDelay`). No randomness — useful for predictable testing.
- **`decorrelated`**: `min(maxDelay, random(baseDelay, prevDelay * 3))`. Uses the previous delay to compute the next one, spreading out retries further over time (AWS-recommended strategy for high-concurrency scenarios).

```typescript
const fetchWithRetry = createSmoothFetch({
  backoff: {
    baseDelay: 100,
    maxDelay: 30000,
    maxRetries: 3,
    jitter: 'equal'
  }
});
```

### Client Error Handling & Alerts

By default, client errors (e.g. `400`, `401`, `403`, `404`, `405`) resolve immediately and bypass the retry loop. If you want to handle these errors gracefully and alert users:

```typescript
import { createSmoothFetch } from '@codingaryan/smoothapi';

const fetchWithRetry = createSmoothFetch({
  fallbackOnNonRetryable: true,
  // Optional: Trigger custom UI logic when a client error happens
  onNonRetryableError: (status, message) => {
    console.log(`Custom callback: Received status ${status}`);
  },
  // Optional: Fallback returned on non-retryable errors
  fallback: { error: "Page not found." }
});
```

* **Default Alerting**: If `fallbackOnNonRetryable` is `true` and no custom `onNonRetryableError` is provided, it logs the warning to `console.error`.
* **Graceful Return**: If no custom `fallback` is configured, it returns a mock `Response` wrapper with the status code and a JSON error body: `{ error: true, status: 404, message: "..." }`. Callers can safely call `.json()`, `.status`, or `.ok` on it without crashing.

### Custom `shouldRetry` Predicate

By default, SmoothAPI retries requests matching status codes in `retryOn` (defaults to `[429, 500, 502, 503, 504]`). You can configure a custom `shouldRetry` predicate function to handle application-level errors (such as GraphQL 200 responses with error payloads) or bypass retries for specific errors:

```typescript
import { createSmoothFetch } from '@codingaryan/smoothapi';

const fetchWithRetry = createSmoothFetch({
  shouldRetry: async (response, error) => {
    // 1. Retry GraphQL error responses even if HTTP status is 200
    if (response?.status === 200) {
      const data = await response.json().catch(() => null);
      if (data?.errors?.length) return true;
    }

    // 2. Bypass retries for non-transient 500s or specific network errors
    if (response?.status === 500) {
      return false;
    }

    // 3. Fallback to default retry condition
    return response ? [429, 502, 503, 504].includes(response.status) : true;
  }
});
```

* **Body Preservation**: On HTTP responses, `response` passed to `shouldRetry` is an internal clone, preserving the original response stream so your application code can still read `.json()` or `.text()`.
* **Async & Sync Support**: The predicate can return `boolean` or `Promise<boolean>`.
* **Fail-Safe**: If `shouldRetry` throws an error, SmoothAPI logs the error safely to `console.error` and falls back to standard retry logic instead of crashing.

### Request Deduplication

When multiple identical requests are made concurrently, SmoothAPI will execute only one network call and share the result with all callers. This reduces unnecessary load on downstream services and prevents exausting computing resources.

**Enable with default key function** (deduplicates by URL):

```typescript
import { createSmoothFetch } from '@codingaryan/smoothapi';

const fetchWithRetry = createSmoothFetch({
  deduplication: {} // Empty object activates deduplication
});

// All three calls share a single network request
const [a, b, c] = await Promise.all([
  fetchWithRetry('http://api.example.com/users/1'),
  fetchWithRetry('http://api.example.com/users/1'),
  fetchWithRetry('http://api.example.com/users/1'),
]);
```

**Custom key function** for advanced coalescing:

```typescript
const fetchWithRetry = createSmoothFetch({
  deduplication: {
    // Deduplicate by method + URL (ignores headers/body)
    keyFn: (url, options) => `${options?.method ?? 'GET'}:${url.toString()}`
  }
});
```

**Opt out of deduplication** for specific requests:

```typescript
const fetchWithRetry = createSmoothFetch({
  deduplication: {
    keyFn: (url, options) => {
      // Skip dedup for POST requests
      if (options?.method === 'POST') return null;
      return url.toString();
    }
  }
});
```

* **Default Behavior**: Deduplicates by URL only (method-agnostic). Concurrent GETs to the same URL are merged.
* **Error Propagation**: If the network call fails, all waiting callers receive the same error.
* **Settlement**: Once a request completes, the next call to the same URL triggers a fresh network request.

### Lifecycle Event Hooks

You can pass callback functions to listen to key events during the request lifecycle. This is particularly useful for logging, metrics, and telemetry.

```typescript
import { createSmoothFetch } from '@codingaryan/smoothapi';

const fetchWithRetry = createSmoothFetch({
  onRetry: (context) => {
    // Fired before a request is retried
    console.warn(`[Attempt ${context.attempt}/${context.maxRetries}] Retrying ${context.domain} in ${context.delayMs}ms. Status: ${context.status}`);
  },
  onCircuitStateChange: (event) => {
    // Fired when the circuit breaker transitions states
    console.warn(`Circuit for ${event.domain} changed from ${event.from} to ${event.to}. Failures: ${event.failureCount}`);
  }
});
```

- **`onRetry(context)`**: Receives `{ attempt, maxRetries, delayMs, status?, error?, url, domain }`. It fires immediately before the delay sleep begins.
- **`onCircuitStateChange(event)`**: Receives `{ domain, from, to, failureCount }`. It fires exactly when the state transitions (`CLOSED` → `OPEN` → `HALF_OPEN` → `CLOSED`).
- **Fail-Safe**: If your hook throws an exception, SmoothAPI catches and logs it internally, ensuring it never crashes your request pipeline.

### AbortController Support

SmoothAPI natively supports `AbortController`, seamlessly propagating cancellation signals through both the active network request and any ongoing exponential backoff delays.

```typescript
import { createSmoothFetch } from '@codingaryan/smoothapi';

const fetchWithRetry = createSmoothFetch({
  backoff: { maxRetries: 3 }
});

const controller = new AbortController();

// Cancel the request (or any ongoing retry delays) after 2 seconds
setTimeout(() => {
  controller.abort();
}, 2000);

try {
  const response = await fetchWithRetry('https://api.example.com/data', {
    signal: controller.signal
  });
  console.log(await response.json());
} catch (err) {
  if (err.name === 'AbortError') {
    console.error("Request cancelled by the user.");
  }
}
```

- **Immediate Halting:** If `controller.abort()` is called while the library is waiting between retries (sleeping), the sleep is immediately interrupted, preventing unnecessary delays.
- **Pre-aborted Signals:** If the signal is already aborted before the fetch is called, the library immediately throws without making any network requests.

## How It Works

1. **Host Extraction:** The domain is automatically extracted from the URL. The circuit breaker state is isolated per host (e.g., `api.github.com` failing won't trip the circuit for `api.stripe.com`).
2. **Circuit Check:** Before making a network request, the breaker checks the state. If it's `OPEN`, the request is blocked instantly (returning your fallback, or throwing a `CircuitOpenError`).
3. **Execution & Retries:** If the response status is in your `retryOn` list, it's counted as a failure and retried with backoff.
4. **Recovery:** After `cooldownMs`, the breaker enters `HALF_OPEN` state. The next request acts as a probe. If it succeeds, the circuit closes. If it fails, it snaps back to `OPEN` immediately.
5. **Memory Management:** The circuit breaker cache is capped at a strict 1,000 domains limit. When exceeded, it automatically sweeps and removes `CLOSED` circuits with zero failures to prevent memory leaks in highly dynamic environments.

## License

MIT
