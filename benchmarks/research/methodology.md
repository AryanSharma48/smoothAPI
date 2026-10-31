# Benchmark Methodology & Experimental Design

## 1. Research Questions

This benchmark suite evaluates a shared-core multi-language SDK architecture (`SmoothAPI`) across five execution paths:
1. **`rust_direct`**: Direct Rust execution (`core/rust`), serving as the native-core theoretical floor.
2. **`ts_native`**: Idiomatic native TypeScript (`packages/smooth-api-ts`).
3. **`ts_napi`**: TypeScript calling the Rust core via Node-API (`bindings/node`).
4. **`py_native`**: Idiomatic native Python (`packages/smooth-api-py`).
5. **`py_pyo3`**: Python calling the Rust core via PyO3 (`bindings/python`, `smoothapi_rs`).

Our experimental design addresses three primary research questions:
- **RQ1 (Microbenchmark & FFI Boundary Cost):** How do pure algorithmic execution times in Direct Rust compare against native host languages (`TypeScript`, `Python`) and their FFI-bound counterparts (`Node-API`, `PyO3`), and when does FFI marshalling overhead exceed computational savings?
- **RQ2 (GIL Interaction & Concurrency Scaling):** In Python's PyO3 binding, when does releasing the Global Interpreter Lock (`py.allow_threads`) improve multi-threaded throughput versus introducing synchronization and `Mutex` contention penalties?
- **RQ3 (End-to-End API Client Translation):** Do microbenchmark speedups translate into measurable throughput, tail-latency (`P50`, `P95`, `P99`), or CPU/memory improvements in a functioning HTTP API client across normal (`200 OK`), intermittent (`429`/`503` retry), and sustained-failure (`OPEN` circuit breaker fast-fail) workloads?

---

## 2. Phase 0: Canonical Differential Verification (`diff-001` $\to$ `diff-003`)

Before measuring performance, all five implementations must be proven behaviorally equivalent across a canonical test vector suite ([`benchmarks/config/differential_vectors.json`](../config/differential_vectors.json)):
- **`diff-001-baseline`**: Executed 83 vectors (415 checks) against the unmodified packages, surfacing **22 behavioral divergences** across overflow handling, `HALF_OPEN` probe concurrency, `429` vs `5xx` error classification, and default jitter selection.
- **`diff-002-normalized`**: Normalized all five implementations to a unified specification (`405/405` normative checks passed; `10/10` host numeric boundary checks preserved separately).
- **`diff-003-audited`**: Resolved RFC 9110 `Retry-After: "0"` compliance (`0 ms` valid), added exact cooldown boundary checks (`t-1`, `t`, `t+1`), added abandoned `HALF_OPEN` probe recovery (`release_probe()` + lease expiry), and verified all 4 jitter modes (`none`, `full`, `equal`, `decorrelated`), achieving **575/575 normative checks passed** (`115/115` per implementation).

---

## 3. Experimental Controls & Statistical Rigor

1. **Calibrated Sample Windows:** Microbenchmark iterations are calibrated so each round runs for hundreds of milliseconds, eliminating OS clock quantization noise.
2. **Compiler & JIT Controls:**
   - **Rust (`--release`):** Both inputs (`black_box(&cfg)`) and mutable state references (`black_box(&mut cb)`) are wrapped in `std::hint::black_box` on every method call (`perf-001b-validation`) to prevent LLVM from constant-propagating state transitions across unrolled loop steps.
   - **TypeScript (Node.js V8) & Python (CPython):** Explicit warm-up phases precede every timed round; loop outputs are accumulated into live sinks.
3. **Counterbalanced Execution Order:** Across all 5 rounds of every experiment, implementation execution order is cyclically shifted (`Round r` shifts start index by `(r - 1) mod N`) to distribute thermal throttling and OS background scheduling evenly.
4. **Reported Metrics:** Every experiment records raw per-round observations in `raw.csv` and aggregates `mean`, `median`, `sd`, `95% CI`, `min`, and `max` in `summary.json`.

---

## 4. Experiment Suite Definitions

### Experiment 1 (`perf-001-microbenchmarks`) & Bounded Validation (`perf-001b-validation`)
- **Workloads:**
  1. `backoff_deterministic`: 5-attempt cycle (`[0, 1, 2, 3, 10]`, `base=100`, `max=30000`, `jitter='none'`).
  2. `retry_policy_evaluation`: 5-scenario cycle (`200`, `404`, `503`, `429 + Retry-After: "5"`, `500 exhausted`).
  3. `circuit_breaker_transitions`: 5-step full lifecycle cycle (`CLOSED` allow $\to$ 2 failures $\to$ `OPEN` block $\to$ cooldown expiry + `HALF_OPEN` probe recovery to `CLOSED`).
- **FFI Boundary Isolation (`perf-001b-validation`):**
  - Measures `noop_native(x: i64) -> i64` across Node-API and PyO3 (`GIL held` vs `GIL released`) to separate fixed FFI call dispatch overhead from argument marshalling and Rust computation.

### Experiment 2 (`perf-002-gil-concurrency`)
- **Implementations:** `py_native`, `py_pyo3_gil_held`, and `py_pyo3_gil_released` (`py.allow_threads`).
- **Thread Counts:** `1, 2, 4, 8` OS threads synchronized via `threading.Barrier(num_threads, action=record_start)` so timing begins atomically when the final thread enters the barrier.
- **Workloads:**
  1. `backoff_concurrent`: Stateless parallel exponential backoff.
  2. `circuit_independent`: Per-thread `NativeCircuitBreaker` instances (no Rust `Mutex` sharing).
  3. `circuit_shared`: Single shared `NativeCircuitBreaker` instance contended by all threads.

### Experiment 3 (`perf-003-end-to-end`)
- **Controlled Local HTTP Server ([`benchmarks/scripts/e2e_server.mjs`](../scripts/e2e_server.mjs)):** Node.js keep-alive HTTP server on `127.0.0.1:3099` eliminating external internet variance while preserving real TCP loopback socket I/O, HTTP parsing, and client middleware execution.
- **Implementations:** `ts_native`, `ts_napi`, `py_native`, and `py_pyo3` (with GIL held per Experiment 2 findings).
- **Scenarios:**
  1. `normal_200` (`400` reqs/round, `40` warmup): Baseline `200 OK` JSON response overhead.
  2. `intermittent_503_429` (`250` logical reqs = `500` HTTP round-trips/round, `30` warmup): 1st attempt deterministically alternates between `503 Service Unavailable` (even request IDs, `1 ms` backoff) and `429 Too Many Requests` with `Retry-After: 0` (odd request IDs, `0 ms` wait); 2nd attempt succeeds with `200 OK`.
  3. `repeated_failures_cb` (`10,000` reqs/round, `20` warmup): Persistent `503` trips the circuit breaker after 3 failures; the remaining `9,997` requests fast-fail in-process via the `OPEN` circuit breaker and return the configured fallback without network I/O.

### Experiment 3b (`perf-003b-fair-fast-fail`): Controlling for Pre-Breaker Host Work
- **Motivation:** In `perf-003`, the native packages (`createSmoothFetch` and `@smooth_api`) parsed URLs (`new URL()` / `urlparse()`), resolved partition keys, and performed `Map`/`dict` lookups before checking the circuit breaker, whereas the initial Rust-backed wrappers (`ts_napi`, `py_pyo3`) held a pre-bound `NativeCircuitBreaker` instance and checked `canRequest` directly.
- **Controlled Design:** `perf-003b-fair-fast-fail` reruns `repeated_failures_cb` (`10,000` reqs/round, `5` counterbalanced rounds) with `--fair` enabled so both Native and Rust-backed clients execute the **exact same pre-breaker execution path**:
  1. URL extraction and parsing (`new URL(urlStr, origin)` in TS; `_extract_url` + `urlparse(url)` in Python).
  2. Circuit-key computation (`getCircuitKey` in TS; `_resolve_circuit_key` in Python).
  3. Domain-keyed `Map`/`dict` lookup with `>1000`-key cleanup guard (`NapiCircuitBreakerState` vs `CircuitBreakerState` in TS; `Pyo3CircuitBreakerState` vs `CircuitBreakerState` in Python).
  4. Circuit-breaker state check (`canRequest` / `can_request`).
  5. Lifecycle hook check and fallback return.
- Only Step 4 (the circuit-breaker state machine implementation) differs.
