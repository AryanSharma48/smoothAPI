# When should I use SmoothAPI?

SmoothAPI is a zero-dependency resilience library for TypeScript and Python. It is designed to provide a unified layer for API protection, including automatic retries, backoff, circuit breaking, deduplication, and fallbacks.

This guide will help you determine whether SmoothAPI is the right abstraction for your application, or if you would be better off using a smaller library or custom implementation.

## Quick Decision Summary

**Use a simpler solution if:**
- You only need one small resilience mechanism (e.g., just basic retries).
- Your application already has an established resilience layer.
- You need highly specialized behavior that SmoothAPI does not provide.

**Consider SmoothAPI when:**
- You want several resilience mechanisms (retries, circuit breaking, fallbacks, deduplication) combined in one abstraction.
- You want a lightweight, zero-runtime-dependency approach.
- You want the same general resilience concepts available across both TypeScript and Python.
- You want to add resilience without redesigning the rest of your application.

## Feature Decision Table

| If you need... | Consider... |
|---|---|
| Only simple retries | A retry library or simple manual implementation |
| Only circuit breaking | A dedicated circuit breaker library |
| Highly custom resilience behavior | Your own custom implementation |
| Several resilience mechanisms together | SmoothAPI |
| Zero runtime dependencies | SmoothAPI |
| TypeScript + Python resilience concepts | SmoothAPI |

## Why use a unified resilience layer?

Developers often end up implementing multiple pieces of API failure handling independently over time:

1. Basic request retries
2. Exponential backoff (to avoid overwhelming servers)
3. Timeout handling
4. Circuit breaking (stopping requests to failing services)
5. Request deduplication
6. Fallback behavior

SmoothAPI provides a unified resilience layer around API calls. It helps isolate downstream failures, provides controlled retry behavior with full jitter, reduces repeated calls to failing services using an isolated FSM circuit breaker, and provides fallback behavior when configured.

## Comparing the Main Approaches

### 1. Just implement retries yourself

Implementing retries yourself is perfectly reasonable for simple scripts or applications with a very small number of external dependencies. 

However, this approach becomes more complex when you need exponential backoff, jitter, retry limits, error classification based on HTTP status codes, circuit state, and fallback behavior. If you find yourself building these out manually across multiple services, a resilience library may be a better choice.

### 2. Use a dedicated retry library

If all you need is retry and backoff, a focused retry library may be the simplest option.

SmoothAPI may make more sense when you need multiple resilience mechanisms (like deduplication and circuit breaking), unified configuration, and broader failure handling without cobbling together multiple libraries.

### 3. Use a dedicated circuit breaker

A dedicated circuit breaker is appropriate if you only need to protect against cascading failures and already have retry mechanisms handled elsewhere. 

If you want circuit breaking alongside other resilience behavior like automatic retries and deduplication, SmoothAPI provides these out of the box in a single configuration.

### 4. Build your own resilience layer

Building your own resilience layer makes sense if you have highly specialized requirements, an existing internal platform with strict organizational conventions, or unusual transport or failure semantics that standard HTTP clients don't cover.

If you don't have these constraints, SmoothAPI can significantly reduce implementation and maintenance effort by providing a drop-in layer for standard resilience patterns.

## Conceptual Example

Here is the difference between a basic retry-only approach and a SmoothAPI resilience layer.

**Basic Manual Retry**
```typescript
async function fetchWithBasicRetry(url: string, retries = 3) {
  for (let i = 0; i < retries; i++) {
    const response = await fetch(url);
    if (response.ok) return response;
    // Missing backoff, jitter, circuit breaking, etc.
  }
  throw new Error("Failed after retries");
}
```

**SmoothAPI (Smart Defaults)**
```typescript
import { createSmoothFetch } from '@codingaryan/smoothapi';

// Out of the box: 3 retries, exponential backoff, circuit breaking
const fetch = createSmoothFetch({});

const response = await fetch('https://api.example.com/data');
```

**SmoothAPI (Fully Customized Layer)**
```typescript
// Opt-in to additional mechanisms like deduplication, fallbacks, or custom thresholds
const customFetch = createSmoothFetch({
  backoff: { baseDelay: 100, maxDelay: 5000, maxRetries: 5 },
  circuitBreaker: { failureThreshold: 5, cooldownMs: 10000 },
  fallback: { data: 'cached fallback' },
  deduplication: {}, 
  timeoutMs: 5000
});
```

## When SmoothAPI may not be the right choice

- **You only need a trivial retry:** A simple `for` loop may be enough.
- **Your organization already has a mature resilience layer:** If your platform team provides an existing standard, use it.
- **You need behavior SmoothAPI does not currently support:** E.g. highly custom retry strategies beyond backoff.
- **You need a transport-specific abstraction:** SmoothAPI wraps HTTP/fetch concepts. If you need gRPC or raw TCP resilience, this isn't it.
- **Adding another abstraction provides no value:** If your application rarely makes external calls and downtime is acceptable.

## When SmoothAPI is a good fit

SmoothAPI is a strong fit when you want:
- **Multiple resilience mechanisms** (retries, circuit breaking, fallbacks) configured together.
- **Consistent handling** of downstream API failures.
- **Lightweight integration** as a drop-in `fetch` wrapper.
- **Zero runtime dependencies** to keep bundle size small.
- **TypeScript/Python availability** for consistent patterns across language stacks.
- To avoid writing and maintaining repeated resilience boilerplate.

## Next Steps

If SmoothAPI looks appropriate for your project:
- [TypeScript Quick Start](../packages/smooth-api-ts/README.md)
- [Python Quick Start](../packages/smooth-api-py/README.md)
- [Configuration Docs](../packages/smooth-api-ts/README.md#advanced-usage-custom-settings)
- [Examples](../examples)

If you are still evaluating the project:
- [Architecture / How It Works](../README.md#how-it-works)
- [Documentation Website](https://smoothapi.org)
