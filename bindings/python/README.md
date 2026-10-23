# SmoothAPI Python Native Bindings (`smoothapi_rs`)

High-performance native Rust extension for SmoothAPI Python using [PyO3](https://pyo3.rs/) and [Maturin](https://www.maturin.rs/), powered by the shared [`smooth-api-core`](../../core/rust) engine.

## Capabilities

- **`calculate_backoff_native`**: Deterministic capped exponential backoff with arithmetic overflow protection.
- **`evaluate_response_native`**: Status code evaluation and `Retry-After` header parsing.
- **`NativeCircuitBreaker`**: High-throughput thread-safe circuit breaker with finite-state machine transitions (`CLOSED` ↔ `OPEN` ↔ `HALF_OPEN`).

## Local Development

```bash
# Build and install into current Python environment
maturin develop

# Build release wheels
maturin build --release
```

