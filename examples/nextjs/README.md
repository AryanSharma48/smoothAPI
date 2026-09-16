# Next.js Example — @codingaryan/smoothapi

A minimal [Next.js](https://nextjs.org/) (App Router, TypeScript) example showing
how to use `@codingaryan/smoothapi` to make calls to an unreliable third-party
API robust. Real upstream services fail intermittently, rate-limit, and go
down completely. This example shows how to use SmoothAPI with Next.js App Router API Routes to protect your app.

## Endpoints in this example

- `/api/unstable-data` — simulates an upstream service that fails randomly.
- `/api/always-fail` — simulates an upstream service that is completely down.
- `/api/robust` — retry + fallback against `/unstable-data`.
- `/api/circuit-demo` — trips the circuit breaker against `/always-fail`.

## How it works

### `/api/robust` — retry + fallback

This route points `createSmoothFetch` at `/unstable-data`, which returns a
503 randomly.

1. It catches the 503 error.
2. It backs off exponentially and retries.
3. If it succeeds, you get the data.
4. If it fails 3 times, you get the fallback data: `{ status: "degraded", ... }`

### `/api/circuit-demo` — circuit breaker

This route points `createSmoothFetch` at `/always-fail`, which always returns
a 503 error.

1. The first 3 requests will be retried (and fail).
2. The circuit breaker trips `OPEN`.
3. The 4th and subsequent requests immediately return the fallback without even trying the network!
4. After the cooldown period (10s), it enters `HALF_OPEN` and tests the endpoint again.

## Running the example

```bash
cd examples/nextjs
npm install
npm run dev
```

Then visit `http://localhost:3000` to interact with the API routes.

Alternatively, you can test it directly via curl:

```bash
curl http://localhost:3000/api/robust
```
---

## Walkthrough

This route points `createResilientFetch` at `/unstable-data`, which returns a
mix of `200`, `429`, and `500` responses. With the default retry settings, a
retryable status (`429`/`500`/...) causes the client to back off and try again
(up to the default number of retries). Because `/unstable-data` never fails
three times in a row, retries usually recover a `200`.

If every attempt fails, a configured `fallback` value
(`{ data: 'cached fallback (stale)' }`) is returned instead of throwing. The
response includes a `source` flag so you can tell where the data came from:

- `"source": "live"` — a real response from the API (with its HTTP `status`).
- `"source": "fallback"` — the stale cached value was served instead.

In practice you'll almost always see `"source": "live"` here: because `/unstable-data`
never fails several times back-to-back, the retries recover a `200`. To see the
`fallback` path actually taken, use `/api/circuit-demo` below. Note also that the
route passes `{ cache: 'no-store' }` so Next.js doesn't cache the response and
hide the API's varying behavior.

The route also sets `onNonRetryableError` to a `console.error` logger so the
library does **not** fall back to its browser `alert()` behavior on the server.

### `/api/circuit-demo` — circuit breaker

This route points `createResilientFetch` at `/always-fail`, which always returns
`500`, with `failureThreshold: 3` and a short `cooldownMs` so the demo is quick.

Call it repeatedly and watch the behavior change:

1. **First call(s)** — the request hits the network and retries each `500`.
   Consecutive failures accumulate and, once the threshold is reached, the
   circuit trips **OPEN**. The response reports `"hitNetwork": true`.
2. **Subsequent calls** — while the circuit is OPEN, requests are
   short-circuited to the `fallback` *without making any network request*. The
   response reports `"hitNetwork": false`.
3. **After the cooldown** — the breaker probes again (HALF_OPEN); since
   `/always-fail` is still down, it re-opens.

The breaker counts **consecutive** failures and **resets on success**. That's
why `/unstable-data` can never trip it (a `200` always clears the count), while
`/always-fail` trips it reliably.

---

## Example requests

```bash
# Retry + fallback demo
curl http://localhost:3000/api/resilient

# Circuit breaker demo — run it several times in a row to see the circuit open
curl http://localhost:3000/api/circuit-demo
curl http://localhost:3000/api/circuit-demo
curl http://localhost:3000/api/circuit-demo
```
