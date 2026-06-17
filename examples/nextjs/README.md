# Next.js Example — @codingaryan/smoothapi

A minimal [Next.js](https://nextjs.org/) (App Router, TypeScript) example showing
how to use `@codingaryan/smoothapi` to make calls to an unreliable third-party
API resilient. Real upstream services fail intermittently, rate-limit, and go
down; this example wraps `fetch` with retries, a fallback value, and a circuit
breaker so your route handlers degrade gracefully instead of erroring out.

It demonstrates two route handlers against the project's chaos **sandbox**
server:

- `/api/resilient` — retry + fallback against `/unstable-data`.
- `/api/circuit-demo` — circuit breaker against `/always-fail`.

---

## Prerequisites & Setup

### 1. Start the sandbox server

The example calls the chaos sandbox on `http://localhost:3001`. From the repo
root:

```bash
cd sandbox
npm install
node server.js
```

Leave this terminal running.

### 2. Run the example

In a second terminal:

```bash
cd examples/nextjs
npm install
npm run dev
```

Then open [http://localhost:3000](http://localhost:3000) and use the two buttons,
or call the routes directly with the curl commands below.

---

## Walkthrough

### `/api/resilient` — retry + fallback

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
