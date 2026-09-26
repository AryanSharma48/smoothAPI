# Browser Example — @codingaryan/smoothapi

A minimal browser-based example demonstrating how to use `@codingaryan/smoothapi` with retries, fallbacks, and circuit breaker protection.

The example interacts with the local sandbox server and provides two demos:

* **Retry Demo** — Uses `/unstable-data` to demonstrate automatic retries and fallback handling.
* **Circuit Breaker Demo** — Uses `/always-fail` to demonstrate circuit breaker behavior and fallback responses.

## Prerequisites

* Node.js 18+
* npm

## Start the Sandbox

From the repository root:

```bash
cd sandbox
npm install
node server.js
```

The sandbox will run on:

```text
http://localhost:3001
```

## Run the Browser Example

Open a second terminal:

```bash
cd examples/browser
npm install
npm run dev
```

Open the URL shown by Vite (typically `http://localhost:5173`).

## Retry Demo

The Retry Demo calls:

```text
http://localhost:3001/unstable-data
```

This endpoint intentionally returns a mix of:

* 200 responses
* 429 responses
* 500 responses

SmoothAPI automatically retries retryable failures and returns the final successful response when available.

## Circuit Breaker Demo

The Circuit Breaker Demo calls:

```text
http://localhost:3001/always-fail
```

This endpoint always returns a failure response.

After enough consecutive failures, the circuit breaker opens and returns the configured fallback immediately without making additional network requests.

## Timeout Demo

The Timeout Demo calls:

```text
http://localhost:3001/delayed?ms=2500
```

With `timeoutMs: 1000` configured, each attempt that takes longer than 1000ms is aborted. After retry attempts are exhausted, SmoothAPI returns the safe fallback payload without hanging the UI.

## Custom Backoff Demo

Demonstrates exponential backoff with equal jitter:

```text
http://localhost:3001/unstable-data
```

Logs each retry attempt and its calculated jittered delay via the `onRetry` callback in real time.

## Features Demonstrated

* Automatic retries
* Exponential backoff with jitter
* Request timeout protection (`timeoutMs`)
* Fallback responses
* Circuit breaker protection
* Browser integration with SmoothAPI
