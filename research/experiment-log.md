# Experiment Log

Immutable record of all benchmark runs with environment, commits, commands, and anomalies.

---

## Experiment `exp-001-pilot`
- **Date:** 2026-10-20
- **Git Commit:** `ac31b18`
- **Objective:** Pilot sanity run with pre-allocated 5-iteration batch looping (eliminating `% 5` modulo from the timed region) to calibrate iteration targets for steady-state 0.5–1.0s sample durations.
- **Workloads:** `backoff_deterministic`, `retry_policy_evaluation`
- **Rounds:** 3 rounds per language (counterbalanced execution order)
- **Status:** **Completed**
- **Output:** [benchmarks/results/exp-001-pilot/](../benchmarks/results/exp-001-pilot/)
- **Observations:** All pre-flight correctness checks passed across Rust, TypeScript, and Python. Batch looping successfully eliminated loop index overhead, establishing calibrated iteration targets (Rust: 200M/100M; TS: 20M/40M; Python: 6M/3M).

---

## Experiment `exp-001`
- **Date:** 2026-10-20
- **Git Commit:** `ac31b18`
- **Objective:** Production-grade baseline microbenchmark comparing pure in-process backoff and policy evaluation across Rust, TypeScript, and Python. Incorporates calibrated iteration counts (targeting 0.5–1.0s sample duration), modulo-free batch looping, `black_box(&config)` to prevent compiler specialization, and sink accumulation.
- **Workloads:** `backoff_deterministic`, `retry_policy_evaluation`
- **Iterations:** Calibrated per language (Rust: 200M/100M; TS: 20M/40M; Python: 6M/3M) $\times$ 5 rounds
- **Status:** **Completed**
- **Output:** [benchmarks/results/exp-001/](../benchmarks/results/exp-001/)
- **Key Results (Medians):**
  - Backoff Calculation: Rust 2.89 ns/op (578 ms sample) | TS 31.01 ns/op (620 ms sample) | Python 111.16 ns/op (667 ms sample)
  - Retry Policy Evaluation: Rust 5.90 ns/op (590 ms sample) | TS 14.11 ns/op (565 ms sample) | Python 253.00 ns/op (759 ms sample)
