# SmoothAPI Benchmark Suite

This directory contains standalone, reproducible benchmark harnesses for measuring the execution performance of the SmoothAPI resilience engine across Rust, TypeScript (Node.js), and Python.

## Structure

```text
benchmarks/
├── config/
│   └── benchmark.json      # Shared workload parameters and test vectors
├── rust/                   # Rust release benchmark runner
├── typescript/             # TypeScript / Node.js benchmark runner
├── python/                 # Python benchmark runner
├── scripts/
│   └── run_all.py          # Master orchestrator with rotation and statistical derivation
└── results/                # Recorded experiment outputs
    └── README.md           # Result format and experiment index
```

## Running Benchmarks

### 1. Run a Short Pilot (Verify stability and correctness)
```bash
python benchmarks/scripts/run_all.py --pilot
```

### 2. Run Full Experiment (`exp-001`)
```bash
python benchmarks/scripts/run_all.py --experiment-id exp-001
```

### 3. Run Individual Language Runners
Each runner can be executed independently with custom iterations and warmups:

- **Rust:**
  ```bash
  cargo run --release --manifest-path benchmarks/rust/Cargo.toml -- --workload backoff_deterministic --iterations 1000000 --round 1
  ```
- **TypeScript:**
  ```bash
  node benchmarks/typescript/bench.mjs --workload backoff_deterministic --iterations 1000000 --round 1
  ```
- **Python:**
  ```bash
  python benchmarks/python/bench.py --workload backoff_deterministic --iterations 1000000 --round 1
  ```

## Measurement Integrity Controls
- **Correctness First:** Every runner executes strict behavioral assertions before entering timed loops. If any calculation differs from expected vectors, the process aborts.
- **DCE Prevention:** Uses `std::hint::black_box` in Rust and sink accumulation in TypeScript/Python.
- **Round Rotation:** The orchestrator shifts language order between rounds to counteract CPU thermals and scheduler skew.
- **Immutability:** Existing experiment directories cannot be overwritten.

---

## Latest Experiment Results (`exp-001`)

![Experiment exp-001 Benchmark Results](../research/figures/exp-001-summary.png)

| Workload | Rust | TypeScript (Node) | Python 3.14 | Speedup vs Python |
|---|:---:|:---:|:---:|:---:|
| **Backoff Calculation** | **2.81 ns/op** (356.0M ops/s) | 35.19 ns/op (28.4M ops/s) | 130.79 ns/op (7.6M ops/s) | **46.6x faster** |
| **Retry Policy Evaluation** | **5.76 ns/op** (173.7M ops/s) | 16.08 ns/op (62.2M ops/s) | 294.15 ns/op (3.4M ops/s) | **51.1x faster** |

*See [research/findings.md](../research/findings.md) for detailed analysis and limitations.*

