# Experiment Log

Immutable record of all benchmark runs with environment, commits, commands, and anomalies.

---

## Experiment `exp-001-pilot`
- **Date:** 2026-10-20
- **Git Commit:** `efcc871`
- **Objective:** Pilot sanity run to verify runner stability, warmup efficacy, and output schema integrity before full measurement.
- **Workloads:** `backoff_deterministic`, `retry_policy_evaluation`
- **Iterations:** 20,000 per round (3 rounds)
- **Status:** **Completed**
- **Output:** [benchmarks/results/exp-001-pilot/](../benchmarks/results/exp-001-pilot/)
- **Notes:** All pre-flight correctness checks passed across Rust, TypeScript, and Python. Round rotation executed without scheduler or encoding issues.

---

## Experiment `exp-001`
- **Date:** 2026-10-20
- **Git Commit:** `efcc871`
- **Objective:** Baseline microbenchmark comparing pure in-process backoff and policy evaluation across Rust, TypeScript, and Python.
- **Workloads:** `backoff_deterministic`, `retry_policy_evaluation`
- **Iterations:** 1,000,000 per round (5 rounds)
- **Status:** **Completed**
- **Output:** [benchmarks/results/exp-001/](../benchmarks/results/exp-001/)
- **Key Results:**
  - Backoff deterministic median: Rust 2.81 ns/op | TS 35.19 ns/op | Python 130.79 ns/op
  - Policy evaluation median: Rust 5.76 ns/op | TS 16.08 ns/op | Python 294.15 ns/op
