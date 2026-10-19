# SmoothAPI Resilience Engine: Performance Research

This directory documents the empirical performance evaluation of a shared Rust resilience core against native TypeScript and Python implementations.

## Research Questions

1. **Computational Cost:** How much execution overhead does retry policy evaluation and exponential backoff introduce across runtimes (compiled native machine code vs. V8 JIT vs. CPython bytecode)?
2. **Binding Overhead:** What is the cost of crossing the native FFI boundary (Node-API / PyO3) relative to pure in-process execution?
3. **Threshold of Benefit:** At what workload volume or system concurrency level does delegating resilience state to a shared Rust core become beneficial?
4. **Consistency & Correctness:** Can a single core guarantee deterministic mathematical parity for backoff intervals and circuit transitions across heterogeneous languages?

## Experiment Directory

| Experiment ID | Date | Workloads Evaluated | Status | Link |
|---|---|---|---|---|
| `exp-001` | 2026-10-20 | Deterministic backoff & retry-policy evaluation | Planned / Baseline | [Results](../benchmarks/results/exp-001/) |

## Structure

- **[methodology.md](./methodology.md):** Experimental design, measurement controls, warmup protocols, and fairness limitations.
- **[experiment-log.md](./experiment-log.md):** Chronological, immutable record of all experiment runs with commit hashes and environment details.
- **[findings.md](./findings.md):** Verified observations, statistical summaries, and limitations grounded in empirical data.
