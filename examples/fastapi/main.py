import os
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI
import httpx

from smooth_api import resilient_api, ResilientConfig
from smooth_api.config import BackoffConfig, CircuitBreakerConfig

# Shared HTTP client for connection pooling
http_client = httpx.AsyncClient(timeout=10.0)

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await http_client.aclose()

app = FastAPI(
    title="SmoothAPI FastAPI Example",
    description="Demonstrates retry handling, circuit breaker behavior, and fallback handling using SmoothAPI.",
    version="1.0.0",
    lifespan=lifespan,
)

SANDBOX_URL = os.getenv("SANDBOX_URL", "http://localhost:3001")

retry_config = ResilientConfig(
    backoff=BackoffConfig(
        base_delay=0.1,
        max_delay=5.0,
        max_retries=3,
    ),
    retry_on=[429, 500, 502, 503, 504],
)

circuit_config = ResilientConfig(
    backoff=BackoffConfig(
        base_delay=0.1,
        max_delay=5.0,
        max_retries=3,
    ),
    circuit_breaker=CircuitBreakerConfig(
        failure_threshold=3,
        cooldown_ms=5000,
    ),
    retry_on=[429, 500, 502, 503, 504],
    fallback={
        "message": "Circuit breaker is open. Returning fallback response."
    },
)


@app.get(
    "/",
    summary="Project Overview",
    description="Returns information about the available SmoothAPI demonstration endpoints.",
)
async def root() -> Dict[str, Any]:
    return {
        "project": "SmoothAPI FastAPI Example",
        "description": "Demonstrates retries, circuit breakers, and fallback handling using SmoothAPI.",
        "documentation": "/docs",
        "endpoints": {
            "retry_demo": "/retry-demo",
            "circuit_demo": "/circuit-demo",
        },
    }


@resilient_api(retry_config)
async def fetch_unstable_data() -> Any:
    response = await http_client.get(f"{SANDBOX_URL}/unstable-data")
    response.raise_for_status()
    return response.json()


@app.get(
    "/retry-demo",
    summary="Retry Handling Example",
    description="Demonstrates SmoothAPI automatically retrying transient failures.",
)
async def retry_demo() -> Dict[str, Any]:
    result = await fetch_unstable_data()

    return {
        "feature": "Retry Handling",
        "source": "upstream-response",
        "endpoint": "/unstable-data",
        "description": "Demonstrates automatic retries for transient failures.",
        "result": result,
    }


@resilient_api(circuit_config)
async def fetch_failing_data() -> Any:
    response = await http_client.get(f"{SANDBOX_URL}/always-fail")
    response.raise_for_status()
    return response


@app.get(
    "/circuit-demo",
    summary="Circuit Breaker Example",
    description="Demonstrates circuit breaker behavior and fallback responses.",
)
async def circuit_demo() -> Dict[str, Any]:
    result = await fetch_failing_data()

    if isinstance(result, httpx.Response):
        return {
            "feature": "Circuit Breaker",
            "source": "upstream-response",
            "endpoint": "/always-fail",
            "status_code": result.status_code,
            "description": "Retries were exhausted before the circuit opened.",
            "result": result.json(),
        }

    return {
        "feature": "Circuit Breaker",
        "source": "fallback",
        "endpoint": "/always-fail",
        "description": "The circuit breaker is open, so the configured fallback response was returned.",
        "result": result,
    }