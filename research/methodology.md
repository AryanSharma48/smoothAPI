# Benchmark Methodology & Experimental Design

## 1. Principles

To produce scientifically defensible data for performance evaluation and publication:

1. **Isolation of Variables:** Microbenchmarks measure only algorithm execution. Network I/O, OS socket creation, and artificial sleep intervals are excluded from computational baselines.
2. **Equivalence of Workload:** Identical numerical inputs, attempt ranges, and decision branches are fed into each language engine.
3. **Control for Compiler & JIT Effects:**
   - **Rust:** Compiled in `--release` with LLVM optimizations. Unused loop results are passed to `std::hint::black_box` to prevent dead-code elimination (DCE).
   - **TypeScript (Node.js):** Executed with unmeasured warm-up iterations to allow V8 to reach optimized tier-2 machine code (TurboFan). Loop outputs are accumulated into a sink variable to prevent DCE.
   - **Python (CPython):** Pre-warmed as a measurement control (ensuring bytecode cache and specialization are warm) before timing starts. Accumulator sink prevents elimination.
4. **Statistical Rigor:** Multiple independent rounds (5 rounds of 1,000,000 iterations each) are measured. We report median, mean, min, max, and standard deviation—never just the single fastest run.
5. **Rotation & Counterbalancing:** The benchmark orchestrator rotates language execution order between rounds (e.g. Round 1: Rust $\to$ TS $\to$ Python; Round 2: TS $\to$ Python $\to$ Rust) to balance CPU thermal throttling and operating system scheduler interference.

---

## 2. Workload Definitions (`exp-001`)

### Workload 1: `backoff_deterministic`
- **Objective:** Measure the CPU cost of exponential calculation with arithmetic overflow protection and ceiling caps.
- **Inputs:** `base_delay = 100`, `max_delay = 30000`, cycled through attempts `[0, 1, 2, 3, 10]`.
- **Mode:** `jitter: none` (deterministic, isolating math from PRNG state).
- **Correctness Criteria:**
  - Attempt 0 $\to$ 100
  - Attempt 1 $\to$ 200
  - Attempt 2 $\to$ 400
  - Attempt 3 $\to$ 800
  - Attempt 10 $\to$ 30,000 (cap verified)

### Workload 2: `retry_policy_evaluation`
- **Objective:** Measure the cost of branching logic, status code verification, and HTTP header parsing.
- **Inputs:** Cycled through 5 standard scenarios:
  1. Status 200 $\to$ `Success` (fast return)
  2. Status 404 $\to$ `Terminal` (non-retryable client error)
  3. Status 503, attempt 0 $\to$ `Retry { delay: 100 }` (retryable error)
  4. Status 429, attempt 0, header `"5"` $\to$ `Retry { delay: 5000 }` (header parse)
  5. Status 500, attempt 3 $\to$ `Exhausted` (attempt limit exceeded)

---

## 3. Explicit Fairness Discrepancies & Limitations

When reviewing results from `exp-001`, the following known differences must be factored into interpretations:

1. **Unit Differences:**
   - TypeScript and Rust natively compute delays in **milliseconds** (`100ms`, `30000ms`).
   - Python operates in **seconds** (`0.1s`, `30.0s`).
   - *Impact:* Python performs floating-point multiplication (`* 1000.0`) when converting to millisecond outputs.
2. **Jitter Implementation:**
   - TypeScript supports full, equal, decorrelated, and none.
   - Python's core package currently implements `random.uniform(0, capped)` (full jitter). To allow fair comparison for deterministic math, a deterministic counterpart is tested in the benchmark harness.
3. **Execution Context:**
   - Pure microbenchmarks measure raw in-process CPU time.
   - They do **not** reflect end-to-end performance in web applications where native binding FFI overhead (Node-API / PyO3) and network latency (10ms–100ms) will dominate execution.
