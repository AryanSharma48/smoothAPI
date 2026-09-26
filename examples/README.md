# SmoothAPI Examples Directory

Welcome to the SmoothAPI examples directory. This directory contains runnable, real-world examples demonstrating how to use SmoothAPI across different runtimes, frameworks, and programming languages (TypeScript and Python).

All examples connect to the local Chaos Sandbox Server running on `http://localhost:3001` to simulate transient network errors, flaky services, hanging endpoints, and downstream outages.

---

## Feature & Stack Matrix

| Example | Runtime / Environment | Framework / Stack | Retries & Backoff | Circuit Breaker | Fallback Handling | Request Timeouts | Deduplication | Local Port |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **[Browser](./browser)** | Client-side Browser / TS | Vite + Vanilla HTML/TS | Supported | Supported | Supported | Supported | Planned | `5173` |
| **[Express](./express)** | Server-side Node.js / TS | Express 5 | Supported | Supported | Supported | Supported | Supported | `3002` |
| **[FastAPI](./fastapi)** | Server-side Python 3.10+ | FastAPI + HTTPX | Supported | Supported | Supported | Supported | Planned | `8000` |
| **[Next.js](./nextjs)** | Fullstack Node.js / TS | Next.js 14 App Router | Supported | Supported | Supported | Supported | Planned | `3000` |

---

## Quick Start

### 1. Start the Chaos Sandbox
The sandbox simulates transient failures, slow endpoints, and outages. From the repository root:

```bash
cd sandbox
npm install
node server.js
```

The sandbox will listen on `http://localhost:3001`. Leave this terminal open.

### 2. Run an Example
Open a second terminal and navigate to your chosen example directory:

* **Browser (Vite)**:
  ```bash
  cd examples/browser
  npm install
  npm run dev
  ```

* **Express**:
  ```bash
  cd examples/express
  npm install
  npm run dev
  ```

* **Next.js**:
  ```bash
  cd examples/nextjs
  npm install
  npm run dev
  ```

* **FastAPI**:
  ```bash
  cd examples/fastapi
  pip install -r requirements.txt
  uvicorn main:app --reload
  ```

---

## Architecture & Port Allocation

Each example runs independently on its designated local port and makes outbound requests to the mock chaos sandbox:

```text
┌────────────────────────────────┐
│   SmoothAPI Example Client     │
│  (Browser, Express, Next, etc) │
└───────────────┬────────────────┘
                │ Outbound fetch() / httpx
                ▼
┌────────────────────────────────┐
│   Chaos Sandbox Server         │
│     http://localhost:3001      │
│                                │
│  • /unstable-data (429/500/200)│
│  • /always-fail   (500 outage) │
│  • /delayed       (slow / lag) │
│  • /health & /reset            │
└────────────────────────────────┘
```

| Service | Port | Description |
| :--- | :--- | :--- |
| **Sandbox Server** | `3001` | Express-based deterministic failure & delay injection server |
| **Browser Example** | `5173` | Interactive Vite single-page application |
| **Express Example** | `3002` | Backend REST API server |
| **Next.js Example** | `3000` | Server-rendered Next.js application with Route Handlers |
| **FastAPI Example** | `8000` | Python async web framework with automatic OpenAPI docs (`/docs`) |

---

## Example Details

### 1. [Browser Example (`examples/browser`)](./browser)
A zero-framework web app demonstrating client-side resilience:
* **Interactive UI**: Buttons to trigger retry loops, circuit breaker tripping, timeout aborts, and exponential backoff.
* **Live Attempt Inspector**: Real-time progress output logging delay increments between attempts.
* **Tech Stack**: TypeScript, Vite.

### 2. [Express Example (`examples/express`)](./express)
A Node.js backend demonstrating how microservices or API gateways use SmoothAPI:
* **Endpoints**:
  * `GET /retry-demo`: Retries transient 429/500 errors with exponential backoff.
  * `GET /circuit-demo`: Trips circuit OPEN after consecutive failures and returns fallback.
  * `GET /dedup-demo`: Makes 3 concurrent identical requests that collapse into 1 upstream call.
  * `GET /timeout-demo`: Aborts slow calls (`timeoutMs: 1000`) and serves fallback data safely.
  * `GET /backoff-demo`: Returns detailed attempt-by-attempt retry history with equal jitter.
* **Tech Stack**: Express 5, TypeScript, TSX.

### 3. [FastAPI Example (`examples/fastapi`)](./fastapi)
A Python async backend service using `smoothapi-py`:
* **Endpoints**:
  * `GET /retry-demo`: Demonstrates `@smooth_api` decorator with automatic async sleep during retries.
  * `GET /circuit-demo`: Circuit breaker protection against service failure.
  * `GET /timeout-demo`: Per-attempt timeout aborts using `timeout_ms`.
  * `GET /backoff-demo`: Backoff tracking with custom `on_retry` handler.
* **Interactive Swagger UI**: Available at `http://localhost:8000/docs`.
* **Tech Stack**: Python 3.10+, FastAPI, Uvicorn, HTTPX.

### 4. [Next.js Example (`examples/nextjs`)](./nextjs)
A modern full-stack web application using Next.js App Router:
* **Route Handlers**:
  * `/api/resilient`: Server-side resilient data fetching with `cache: 'no-store'`.
  * `/api/circuit-demo`: Shared circuit breaker state across route invocations.
  * `/api/timeout`: Request timeout abort with fallback.
  * `/api/backoff`: Jittered exponential backoff with retry history metrics.
* **Tech Stack**: Next.js 14, React 18, TypeScript.

---

## The Chaos Sandbox Server

The sandbox server (`sandbox/server.js`) runs on `http://localhost:3001` and provides deterministic chaos behavior:

| Endpoint | Behavior | Purpose |
| :--- | :--- | :--- |
| `GET /unstable-data` | Deterministically fails (multiples of 3 return `500`, multiples of 5 return `429`, otherwise `200`). | Testing retries and jittered exponential backoff recovery. |
| `GET /always-fail` | Always returns `500 Internal Server Error`. | Testing consecutive failure accumulation and circuit breaker state (`CLOSED` -> `OPEN` -> `HALF_OPEN`). |
| `GET /delayed?ms=2500`| Delays the HTTP response by specified milliseconds (default `3000ms`). | Testing per-request timeout aborts (`timeoutMs`) and client cancellations. |
| `GET /health` | Always returns `200 OK` with the current internal request count. | Smoke testing, health checks, and deduplication verification. |
| `GET /reset` | Resets the request counter to zero. | Clean test setup between test runs. |

To run the sandbox standalone:
```bash
cd sandbox
npm install
node server.js
```
