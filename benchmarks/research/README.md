# SmoothAPI Resilience Engine: Performance Research

> **Working Paper Title:**  
> *Evaluating a Shared Rust-Based Resilience Engine Across TypeScript and Python: FFI Overhead, Performance, and Behavioural Equivalence*

This research investigates whether exposing a shared Rust API-resilience engine through native bindings (`Node-API` and `PyO3`) is worthwhile when evaluated against equivalent, pure native-language implementations in TypeScript and Python.

---

## 1. Central Research Question

> **Under what conditions does exposing a shared Rust-based API resilience engine through native bindings improve the performance of TypeScript and Python implementations, compared with equivalent native-language implementations, while preserving their observable behaviour?**

---

## 2. Testable Research Questions

| ID | Focus | Research Question | Key Investigation Points |
| :---: | :--- | :--- | :--- |
| **RQ1** | **Native Binding Overhead & Break-Even Crossover** | *What is the performance cost of Node-API and PyO3 bindings, and under what conditions does Rust-backed execution outperform native TypeScript and Python implementations?* | • Cost of crossing the FFI boundary.<br>• Latency and throughput of individual resilience operations.<br>• How operation complexity affects relative overhead.<br>• Break-even point where Rust's speed outpaces FFI serialization/marshaling cost. |
| **RQ2** | **Realistic API-Client Workloads & Concurrency** | *How does the shared Rust core affect performance and resource consumption in complete API-client workloads under different concurrency and failure conditions?* | • Request-processing latency and throughput under concurrent loads.<br>• CPU and memory footprint across runtimes.<br>• Node.js event-loop impact.<br>• Controlled local fault injection (transient failures, 429 rate limits, repeated outages) keeping HTTP transport in native language. |
| **RQ3** | **Cross-Language Behavioural Equivalence** | *Does the shared Rust implementation preserve behavioural equivalence with the native TypeScript and Python implementations?* | • Identical retry decisions and attempt sequences.<br>• Backoff delays and PRNG-seeded jitter behavior.<br>• Circuit-breaker state transitions (`CLOSED` $\leftrightarrow$ `OPEN` $\leftrightarrow$ `HALF_OPEN`).<br>• Correct handling of status codes, limits, and `Retry-After`.<br>• Differential testing under concurrent state changes. |

---

## 3. Implementation Comparison Matrix

To isolate the FFI cost from computation and I/O, experiments evaluate 5 matched paths:

| Implementation | Runtime / Boundary | Purpose |
| :--- | :--- | :--- |
| **Direct Rust** | Native LLVM machine code | Establishes the native-core reference baseline. |
| **Native TypeScript** | Node.js (V8 TurboFan JIT) | Establishes the pure TypeScript baseline. |
| **TypeScript $\to$ Node-API $\to$ Rust** | V8 C++ / Node-API bridge | Measures the Rust-backed TypeScript path and FFI tax. |
| **Native Python** | CPython 3.14 Bytecode | Establishes the pure Python baseline. |
| **Python $\to$ PyO3 $\to$ Rust** | Python C-Extension API / PyO3 | Measures the Rust-backed Python path and FFI tax. |

### Core Resilience Operations Under Evaluation:
1. **Backoff Calculation:** Exponential progression, caps, and PRNG-seeded jitter strategies.
2. **Retry-Policy Evaluation:** Status code classification, header parsing (`Retry-After`), and attempt limit checks.
3. **Circuit-Breaker State Machine:** Dynamic state transitions, failure counters, sliding windows, and half-open multi-probe anti-flapping.
4. **End-to-End API Client:** Realistic network resilience wrapper under local fault injection.

---

## 4. Literature Grounding & Research Gap

Prior academic literature covers related intersections, but leaves open the specific convergence addressed by SmoothAPI:

| Prior Research | Key Finding | What It Leaves Open for SmoothAPI |
| :--- | :--- | :--- |
| **Küsters & van der Aalst (2024)** | Shared Rust libraries can expose algorithms to multiple language ecosystems. | Whether this architecture benefits fine-grained, latency-critical API-resilience operations through Node-API and PyO3. |
| **do Amaral et al. (2025)** | Measures PyO3, CFFI, and ctypes function-call overhead and chunked calls. | Evaluates generic calls; leaves open resilience-specific workloads, stateful circuit breakers, and a matched TypeScript/Node-API comparison. |
| **Schofield & Hodson (2025)** | Compares Rust-backed Python data structures against native Python. | Investigates collections; leaves open stateful distributed systems resilience and cross-language equivalence. |
| **Aderaldo et al. (2024–2026)** *(ResilienceBench)* | Evaluates retry and circuit-breaker performance/reliability trade-offs under failure rates. | Focuses on configuration effects; leaves open the cost of implementing resilience natively vs. calling a shared Rust engine across an FFI. |

---

## 5. Explicit Non-Goals & Scope Boundaries

To maintain scientific rigor and prevent scope dilution, the following directions are **explicitly excluded** from central research questions:

| Excluded Topic | Justification |
| :--- | :--- |
| *"Is Rust faster than Python or TypeScript in raw compute?"* | Too generic; trivial benchmark without application context. |
| *"Do retries and circuit breakers improve reliability?"* | Already comprehensively settled in distributed systems literature. |
| *"Does jitter prevent thundering herds / retry storms?"* | Already covered by established cloud architecture and resilience research. |
| *"Designing new retry-budget algorithms"* | Separate research area (addressed by 2026 retry amplification studies). |
| *"Treating batching as the primary contribution"* | In real-world API clients, resilience decisions occur per outgoing request; batching will be measured as a dimension, not the primary claim. |

> **Secondary Engineering Evaluation (Non-RQ):** Binary size (`.node` DLLs / `.so`), packaging/installation friction, cold-start latency, and maintenance complexity will be documented as engineering trade-offs rather than academic research questions.

---

## 6. Experiment Roadmap

| Experiment ID | Focus | Mapped RQ | Status | Link |
| :---: | :--- | :---: | :---: | :---: |
| **`exp-001`** | **Baseline In-Process Computation:** Calibrated pure execution across Rust, TS, and Python. | RQ1 (Reference) | **Completed** | [Results](../results/exp-001/) |
| **`exp-002`** | **FFI Boundary Overhead:** Direct comparison of pure TS vs `Node-API` bridge (`bindings/node`) across single-call and chunked workloads. | RQ1 | **Planned** | `exp-002/` |
| **`exp-003`** | **Stateful Circuit Breaker Transitions:** Multi-domain state machine evaluation across native and bound runtimes. | RQ1, RQ3 | **Planned** | `exp-003/` |
| **`exp-004`** | **Realistic API Client & Concurrency:** End-to-end client under local fault injection measuring latency, throughput, and CPU/memory. | RQ2, RQ3 | **Planned** | `exp-004/` |

---

## Structure

- **[methodology.md](./methodology.md):** Experimental design, measurement controls, warmup protocols, and fairness limitations.
- **[experiment-log.md](./experiment-log.md):** Chronological, immutable record of all experiment runs with commit hashes and environment details.
- **[findings.md](./findings.md):** Verified observations, statistical summaries, and limitations grounded in empirical data.
