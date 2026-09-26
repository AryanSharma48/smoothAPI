# SmoothAPI Express Example

This example demonstrates how to integrate SmoothAPI into an Express.js application to make outbound API requests more resilient using retries, circuit breakers, and fallback responses.

## Features

- Automatic retries for transient failures
- Circuit breaker protection
- Graceful fallback responses
- Request deduplication for concurrent identical requests
- Express.js integration using SmoothAPI

---

## Prerequisites

- Node.js 18+
- npm 9+

---

## Install Dependencies

From the example directory:

```bash
cd examples/express
npm install
```

---

## Start the Sandbox Server

The example depends on the repository sandbox server, which simulates flaky and failing upstream APIs.

From the repository root:

```bash
cd sandbox
npm install
node server.js
```

The sandbox will start on:

```text
http://localhost:3001
```

---

## Run the Express Example

In a second terminal, from the example directory:

```bash
cd examples/express
npm run dev
```

The Express app will be available at:

```text
http://localhost:3002
```

---

## Available Endpoints

### GET /

Returns a simple intro message.

### GET /health

Returns a basic readiness response for the example app.

### GET /retry-demo

Demonstrates SmoothAPI's retry mechanism by calling the sandbox's unstable endpoint:

```text
GET http://localhost:3001/unstable-data
```

SmoothAPI retries transient failures before returning a successful response or falling back when retries are exhausted.

### GET /circuit-demo

Demonstrates SmoothAPI's circuit breaker and fallback behavior by calling the sandbox's always-failing endpoint:

```text
GET http://localhost:3001/always-fail
```

After repeated failures, the circuit breaker opens and returns the configured fallback response immediately without making another network request.

### GET /dedup-demo

Demonstrates SmoothAPI's request deduplication by making three identical
requests concurrently using `Promise.all()`.

All three requests target the same sandbox URL:

```text
GET http://localhost:3001/health
```

### GET /timeout-demo

Demonstrates per-request timeouts (`timeoutMs: 1000`) and graceful fallback recovery when downstream endpoints hang:

```text
GET http://localhost:3001/delayed?ms=2500
```

Each attempt aborts after 1000ms. Once retries are exhausted, SmoothAPI safely returns the fallback payload.

### GET /backoff-demo

Demonstrates exponential backoff with equal jitter and real-time attempt tracking:

```text
GET http://localhost:3001/unstable-data
```

Returns the retry timeline and delay metrics recorded by the `onRetry` hook.

---

## Example Requests

You can test the endpoints with curl:

```bash
curl http://localhost:3002/health
curl http://localhost:3002/retry-demo
curl http://localhost:3002/circuit-demo
curl http://localhost:3002/dedup-demo
curl http://localhost:3002/timeout-demo
curl http://localhost:3002/backoff-demo
```

Or you could open the endpoints on any browser

---

## Project Structure

```text
express/
├── server.ts
├── package.json
└── README.md
```
