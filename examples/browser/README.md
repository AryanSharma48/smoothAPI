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

## Features Demonstrated

* Automatic retries
* Exponential backoff
* Fallback responses
* Circuit breaker protection
* Browser integration with SmoothAPI
