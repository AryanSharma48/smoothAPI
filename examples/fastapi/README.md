# SmoothAPI FastAPI Example

This example demonstrates how to integrate **SmoothAPI** into a FastAPI application to make outbound API requests more resilient using retries, circuit breakers, and fallback responses.

## Features

- Automatic retries for transient failures
- Circuit breaker protection
- Graceful fallback responses
- Async FastAPI integration using `httpx`

---

## Prerequisites

- Python 3.10+
- Node.js (for the sandbox server)

---

## Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Start the Sandbox Server

From the repository root:

```bash
cd sandbox
npm install
node server.js
```

The sandbox will start on:

```
http://localhost:3001
```

---

## Run the FastAPI Example

From the `examples/fastapi` directory:

```bash
uvicorn main:app --reload
```

The API will be available at:

```
http://127.0.0.1:8000
```

Interactive API documentation:

```
http://127.0.0.1:8000/docs
```

---

## Available Endpoints

### `GET /`

Returns basic information about the example application.

---

### `GET /retry-demo`

Demonstrates SmoothAPI's retry mechanism by calling the sandbox's unstable endpoint.

Target endpoint:

```
GET http://localhost:3001/unstable-data
```

SmoothAPI automatically retries transient failures before returning a successful response.

---

### `GET /circuit-demo`

Demonstrates SmoothAPI's circuit breaker and fallback behavior.

Target endpoint:

```
GET http://localhost:3001/always-fail
```

After repeated failures, the circuit breaker opens and returns the configured fallback response immediately without making another network request.

---

## Project Structure

```
fastapi/
├── main.py
├── requirements.txt
└── README.md
```