# Empirical Findings & Data Analysis

This document records observations and interpretations drawn directly from measured benchmark experiments.

> **Research Integrity Standard:** All claims and comparisons recorded here are grounded in data from `benchmarks/results/` and cite their specific experiment ID. No hypothetical or illustrative performance values are presented as findings.

---

## Experiment `exp-001`: Baseline Computation Performance (Calibrated Durations)

- **Date:** 2026-10-20
- **Hardware:** AMD Ryzen 7 7435HS (8 Cores, 16 Logical Processors) | Windows 11
- **Toolchains:** `rustc 1.93.1 (opt-level=3)` | `Node.js v22.20.0 (V8)` | `CPython 3.14.0`
- **Methodological Controls:**
  - **Calibrated Durations:** Each sample was calibrated to execute for **0.55 – 0.76 seconds**, eliminating timer quantization and governor scaling noise.
  - **Batch Iteration (Modulo Removal):** Test vectors pre-cycled in 5-iteration batches outside timed regions, eliminating `% 5` modulo bytecode/instruction overhead.
  - **Compiler Specialization Barrier:** Rust runner passes `black_box(&config)` into `calculate_backoff` and `evaluate_response`.
  - **Sink Accumulation & DCE Prevention:** All three runtimes accumulate return values into numeric sinks with compiler DCE guards.
  - **Counterbalanced Execution Order:** Language execution order was rotated across all 5 rounds.
- **Data Source:** [benchmarks/results/exp-001/summary.json](../benchmarks/results/exp-001/summary.json) & [raw.csv](../benchmarks/results/exp-001/raw.csv)

### Summary Table

| Workload | Language | Sample Iterations | Median Latency | Stdev | Spread (Min–Max) | Spread % | Throughput (ops/sec) | Sample Duration |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Backoff Calculation** | **Rust** | 200,000,000 | **2.89 ns/op** | $\pm 0.07$ ns | 2.72 – 2.91 ns | 6.55% | **345,815,665** | 578.3 ms |
| *(Deterministic math)* | **TypeScript** | 20,000,000 | 31.01 ns/op | $\pm 0.17$ ns | 30.81 – 31.20 ns | 1.26% | 32,246,596 | 620.2 ms |
| | **Python** | 6,000,000 | 111.16 ns/op | $\pm 2.76$ ns | 109.79 – 117.61 ns | 7.04% | 8,996,185 | 666.9 ms |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Retry Policy Evaluation** | **Rust** | 100,000,000 | **5.90 ns/op** | $\pm 0.16$ ns | 5.79 – 6.22 ns | 7.23% | **169,489,773** | 590.0 ms |
| *(Branching & parsing)* | **TypeScript** | 40,000,000 | 14.11 ns/op | $\pm 0.15$ ns | 13.97 – 14.37 ns | 2.86% | 70,850,495 | 564.6 ms |
| | **Python** | 3,000,000 | 253.00 ns/op | $\pm 1.64$ ns | 250.28 – 254.27 ns | 1.58% | 3,952,617 | 759.0 ms |

---

### Graphical Visualizations

![Experiment exp-001 Summary](./figures/exp-001-summary.png)

<p align="center">
  <img src="./figures/exp-001-latency.png" alt="Latency Comparison" width="48%" />
  <img src="./figures/exp-001-throughput.png" alt="Throughput Comparison" width="48%" />
</p>

---

### Key Empirical Observations

1. **Arithmetic & Branching Throughput (Backoff):**
   - Rust executes deterministic exponential backoff in **2.89 ns/op**, sustaining over 345 million operations per second on a single thread.
   - V8 (Node.js) JIT compiles the power calculation (`2 ** attempt`) and `Math.min` efficiently, completing in **31.01 ns/op** (approx. 32.2M ops/sec) with an exceptionally low spread of **1.26%**.
   - CPython 3.14 bytecode evaluation takes **111.16 ns/op** (approx. 9.0M ops/sec). Eliminating the inner-loop modulo division reduced Python latency by 15% compared to preliminary untuned loops.

2. **Branching & State Evaluation (Retry Policy):**
   - In policy evaluation (handling status code checks, attempt limit evaluations, and header string parsing), TypeScript performs at **14.11 ns/op** (within 2.39x of native Rust). V8's inline caching optimizes array inclusion and dictionary creation heavily.
   - Rust executes the enum matching, `should_retry` comparison, and string parsing in **5.90 ns/op** (169.5M ops/sec).
   - CPython 3.14 takes **253.00 ns/op** (3.95M ops/sec), showing runtime overhead from dynamic dictionary allocation and runtime dispatch.

3. **Steady-State Stability (0.55 – 0.76s per Sample):**
   - Calibrating each sample to run for >500 ms eliminated transient warm-up and thread scheduling noise, resulting in standard deviations below $\pm 0.17$ ns for Rust and TypeScript.

---

### Critical Limitations & Non-Claims

> [!WARNING]
> **Pure computation $\neq$ End-to-end network speed:**
> While Rust is 10.7x faster than Node.js and 38.4x faster than Python at calculating backoff in-process, this pure computation difference represents **less than 0.00003 ms**. 
> In a real web application with a 50ms HTTP network request, calculating backoff in 2.89ns vs. 31ns vs. 111ns has zero measurable impact on end-user latency.
> 
> Therefore, **the primary value of a Rust core at low scale is deterministic cross-language behavioral parity and safety, not microsecond latency savings.**
> Rust-backed performance gains will only become relevant when native binding overhead (FFI) is measured and high-concurrency request coalescing / deduplication (SingleFlight pattern) is evaluated under load.
