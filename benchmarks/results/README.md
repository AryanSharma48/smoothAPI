# Benchmark Results Index

This directory holds machine-readable measurements, differential verification reports, and statistical summaries for each recorded experiment.

## Immutability Policy
- Never overwrite an existing experiment directory.
- Repeated runs or methodological refinements receive a new ID.

## Recorded Experiments

| Experiment ID | Category | Description | Primary Output |
|---|---|---|---|
| [`exp-001`](./exp-001/summary.json) | Preliminary Baseline | Calibrated pure-language computation baseline (`Rust`, `TypeScript`, `Python`) for backoff and retry evaluation | `summary.json`, `raw.csv` |
| [`diff-001-baseline`](./diff-001-baseline/report.json) | Differential Testing | Pre-normalization cross-language verification across 5 implementations (`393/415` passed; 22 mismatches exposed) | `report.json` |
| [`diff-002-normalized`](./diff-002-normalized/report.json) | Differential Testing | Post-normalization verification (`405/405` normative + `10/10` host boundary checks) | `report.json` |
| [`diff-003-audited`](./diff-003-audited/report.json) | Differential Testing | Standards-audited verification including RFC 9110 `Retry-After: "0"`, exact cooldown boundaries (`t-1, t, t+1`), abandoned `HALF_OPEN` probe recovery, and 4 jitter strategies (`575/575` normative checks passed) | `report.json` |
| [`perf-001-microbenchmarks`](./perf-001-microbenchmarks/summary.json) | Experiment 1 | 5-way core operation microbenchmarks (`rust_direct`, `ts_native`, `ts_napi`, `py_native`, `py_pyo3`) across backoff, retry evaluation, and circuit breaker transitions | `summary.json`, `raw.csv` |
| [`perf-001b-validation`](./perf-001b-validation/summary.json) | Methodological Validation | Bounded validation isolating `black_box(&mut cb)` Direct Rust circuit-breaker latency (`2.03 ns/op`) and raw FFI no-op round-trip overhead (`Node-API` vs `PyO3`) | `summary.json`, `raw.csv` |
| [`perf-002-gil-concurrency`](./perf-002-gil-concurrency/summary.json) | Experiment 2 | Multi-threaded Python concurrency (`1, 2, 4, 8` threads) comparing `py_native`, `py_pyo3_gil_held`, and `py_pyo3_gil_released` across stateless, independent stateful, and shared `Mutex` workloads | `summary.json`, `raw.csv` |
| [`perf-003-end-to-end`](./perf-003-end-to-end/summary.json) | Experiment 3 | End-to-end API client benchmark (`ts_native`, `ts_napi`, `py_native`, `py_pyo3`) against a local keep-alive HTTP server across `normal_200`, `intermittent_503_429`, and `repeated_failures_cb` | `summary.json`, `raw.csv` |
| [`perf-003b-fair-fast-fail`](./perf-003b-fair-fast-fail/summary.json) | Experiment 3b | Fair fast-fail isolation (`repeated_failures_cb`) enforcing identical URL parsing, key extraction, `Map`/`dict` lookup, and fallback pre-work across native and Rust-backed clients | `summary.json`, `raw.csv` |

## Directory Schema per Performance Experiment

```text
<experiment-id>/
├── metadata.json   # Machine details, OS, toolchain versions, and configuration
├── raw.csv         # Per-round measurements across all iterations and implementations
└── summary.json    # Derived statistics (mean, median, min, max, stdev, 95% CI, speedup ratios)
```
