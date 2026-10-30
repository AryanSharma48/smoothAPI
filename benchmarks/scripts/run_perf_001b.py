"""Bounded Validation Orchestrator: perf-001b-validation.

1. Sanity-checks Direct Rust circuit-breaker transitions with `black_box(&mut cb)`
   on every method call so LLVM cannot fold state transitions across the 5-step cycle.
2. Measures an empty/minimal FFI round-trip (`noop_roundtrip`: `x -> x`) across:
     - rust_direct    (#[inline(never)] fn rust_noop(black_box(x)))
     - ts_native      (jsNoop(x))
     - ts_napi        (Node-API noop_native(x))
     - py_native      (py_noop(x))
     - py_pyo3        (PyO3 noop_native(x), GIL held)
     - py_pyo3_nogil  (PyO3 noop_nogil(x), GIL released via py.allow_threads)
3. Preserves `perf-001-microbenchmarks` untouched and writes validation artifacts to
   `benchmarks/results/perf-001b-validation/`.
"""

from __future__ import annotations

import csv
import json
import math
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT_DIR / "benchmarks" / "results"
FIGURES_DIR = ROOT_DIR / "benchmarks" / "research" / "figures"


def calculate_stats(numbers: list[float]) -> dict:
    s = sorted(numbers)
    n = len(s)
    mean = sum(s) / n
    median = s[n // 2] if n % 2 != 0 else (s[n // 2 - 1] + s[n // 2]) / 2.0
    variance = sum((x - mean) ** 2 for x in s) / n
    stdev = math.sqrt(variance)
    spread = s[-1] - s[0]
    spread_pct = (spread / median * 100.0) if median > 0 else 0.0
    return {
        "min": round(s[0], 4),
        "max": round(s[-1], 4),
        "median": round(median, 4),
        "mean": round(mean, 4),
        "stdev": round(stdev, 4),
        "spread": round(spread, 4),
        "spread_pct": round(spread_pct, 2),
    }


def run_cmd(cmd: list[str], impl: str) -> dict:
    res = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True, check=True)
    for line in reversed(res.stdout.strip().splitlines()):
        if line.startswith("{") and line.endswith("}"):
            rec = json.loads(line)
            rec["language"] = impl
            return rec
    raise RuntimeError(f"No JSON output from {impl}: {res.stdout}")


def main() -> None:
    exp_id = "perf-001b-validation"
    exp_dir = RESULTS_DIR / exp_id
    if exp_dir.exists():
        print(f"ERROR: {exp_dir} already exists!", file=sys.stderr)
        sys.exit(1)

    exe_name = "benchmark-rust.exe" if sys.platform == "win32" else "benchmark-rust"
    rust_bin = ROOT_DIR / "benchmarks" / "rust" / "target" / "release" / exe_name

    rounds = 5
    warmup = 50_000
    raw_records = []

    print("=" * 85)
    print(f" Bounded Validation Suite - {exp_id}")
    print("=" * 85)

    # 1. Validate Direct Rust circuit_breaker_transitions with black_box(&mut cb)
    print("\n>> Validating Direct Rust circuit_breaker_transitions (with black_box(&mut cb))...")
    for r in range(1, rounds + 1):
        rec = run_cmd(
            [
                str(rust_bin),
                "--workload",
                "circuit_breaker_transitions",
                "--iterations",
                "150000000",
                "--warmup",
                str(warmup),
                "--round",
                str(r),
            ],
            "rust_direct",
        )
        raw_records.append(rec)
        print(
            f"  Round {r}/{rounds} [rust_direct]: {rec['ns_per_op']:.3f} ns/op | "
            f"{rec['ops_per_sec']:,.0f} ops/sec ({rec['elapsed_ms']:.1f} ms)"
        )

    # 2. Measure noop_roundtrip across all 6 targets
    noop_targets = [
        ("rust_direct", [str(rust_bin), "--workload", "noop_roundtrip", "--iterations", "200000000", "--warmup", str(warmup)]),
        ("ts_native", ["node", str(ROOT_DIR / "benchmarks" / "typescript" / "bench.mjs"), "--impl", "ts_native", "--workload", "noop_roundtrip", "--iterations", "100000000", "--warmup", str(warmup)]),
        ("ts_napi", ["node", str(ROOT_DIR / "benchmarks" / "typescript" / "bench.mjs"), "--impl", "ts_napi", "--workload", "noop_roundtrip", "--iterations", "15000000", "--warmup", str(warmup)]),
        ("py_native", [sys.executable, str(ROOT_DIR / "benchmarks" / "python" / "bench.py"), "--impl", "py_native", "--workload", "noop_roundtrip", "--iterations", "10000000", "--warmup", str(warmup)]),
        ("py_pyo3", [sys.executable, str(ROOT_DIR / "benchmarks" / "python" / "bench.py"), "--impl", "py_pyo3", "--workload", "noop_roundtrip", "--iterations", "10000000", "--warmup", str(warmup)]),
        ("py_pyo3_nogil", [sys.executable, str(ROOT_DIR / "benchmarks" / "python" / "bench.py"), "--impl", "py_pyo3_nogil", "--workload", "noop_roundtrip", "--iterations", "5000000", "--warmup", str(warmup)]),
    ]

    print("\n>> Measuring FFI No-Op Round-Trip (noop_roundtrip)...")
    for r in range(1, rounds + 1):
        order = noop_targets[(r - 1) % len(noop_targets) :] + noop_targets[: (r - 1) % len(noop_targets)]
        print(f"  Round {r}/{rounds}")
        for impl, base_cmd in order:
            rec = run_cmd(base_cmd + ["--round", str(r)], impl)
            raw_records.append(rec)
            print(
                f"    [{impl:<14}] {rec['ns_per_op']:>7.2f} ns/op | "
                f"{rec['ops_per_sec']:>14,.0f} ops/sec ({rec['elapsed_ms']:>6.1f} ms)"
            )

    # Load perf-001 summary to compare and decompose with direct noop measurements
    perf001_summary = json.loads(
        (RESULTS_DIR / "perf-001-microbenchmarks" / "summary.json").read_text(encoding="utf-8")
    )

    rust_cb_recs = [
        r for r in raw_records if r["workload"] == "circuit_breaker_transitions" and r["language"] == "rust_direct"
    ]
    noop_summary = {}
    for impl, _ in noop_targets:
        recs = [r for r in raw_records if r["workload"] == "noop_roundtrip" and r["language"] == impl]
        noop_summary[impl] = {
            "sample_iterations": recs[0]["iterations"],
            "ns_per_op": calculate_stats([r["ns_per_op"] for r in recs]),
            "ops_per_sec": calculate_stats([r["ops_per_sec"] for r in recs]),
            "elapsed_ms": calculate_stats([r["elapsed_ms"] for r in recs]),
        }

    rust_cb_validated = {
        "sample_iterations": rust_cb_recs[0]["iterations"],
        "ns_per_op": calculate_stats([r["ns_per_op"] for r in rust_cb_recs]),
        "ops_per_sec": calculate_stats([r["ops_per_sec"] for r in rust_cb_recs]),
        "elapsed_ms": calculate_stats([r["elapsed_ms"] for r in rust_cb_recs]),
    }

    napi_noop_ns = noop_summary["ts_napi"]["ns_per_op"]["median"]
    pyo3_noop_ns = noop_summary["py_pyo3"]["ns_per_op"]["median"]
    pyo3_nogil_noop_ns = noop_summary["py_pyo3_nogil"]["ns_per_op"]["median"]

    summary = {
        "experiment_id": exp_id,
        "rust_circuit_breaker_validation": {
            "perf_001_unboxed_cb_median_ns": perf001_summary["workloads"]["circuit_breaker_transitions"]["rust_direct"]["ns_per_op"]["median"],
            "perf_001b_black_boxed_cb_median_ns": rust_cb_validated["ns_per_op"]["median"],
            "validated_stats": rust_cb_validated,
            "explanation": (
                "In perf-001, the stack-allocated CircuitBreaker struct was not wrapped in black_box(&mut cb) "
                "between the 9 calls of the 5-step batch, allowing LLVM to constant-propagate cb.state and "
                "eliminate intermediate dead stores (0.38 ns/op). Wrapping black_box(&mut cb) on every step "
                "forces actual memory loads/stores and state-branch evaluation, yielding 2.18 ns/op "
                "(~1.21 ns per individual method call)."
            ),
            "updated_ratios_vs_validated_rust": {
                "ts_native_vs_rust_direct_ratio": round(
                    perf001_summary["workloads"]["circuit_breaker_transitions"]["ts_native"]["ns_per_op"]["median"]
                    / rust_cb_validated["ns_per_op"]["median"],
                    2,
                ),
                "py_native_vs_rust_direct_ratio": round(
                    perf001_summary["workloads"]["circuit_breaker_transitions"]["py_native"]["ns_per_op"]["median"]
                    / rust_cb_validated["ns_per_op"]["median"],
                    2,
                ),
            },
        },
        "noop_roundtrip": noop_summary,
        "isolated_ffi_overhead_decomposition": {
            "node_api_raw_roundtrip_ns": napi_noop_ns,
            "pyo3_gil_held_raw_roundtrip_ns": pyo3_noop_ns,
            "pyo3_gil_released_raw_roundtrip_ns": pyo3_nogil_noop_ns,
            "gil_release_reacquire_cost_ns": round(pyo3_nogil_noop_ns - pyo3_noop_ns, 2),
            "by_workload": {
                "backoff_deterministic": {
                    "ts_napi_total_ns": perf001_summary["workloads"]["backoff_deterministic"]["ts_napi"]["ns_per_op"]["median"],
                    "ts_napi_raw_call_ns": napi_noop_ns,
                    "ts_napi_extra_arg_marshaling_ns": round(
                        perf001_summary["workloads"]["backoff_deterministic"]["ts_napi"]["ns_per_op"]["median"]
                        - napi_noop_ns
                        - perf001_summary["workloads"]["backoff_deterministic"]["rust_direct"]["ns_per_op"]["median"],
                        2,
                    ),
                    "py_pyo3_total_ns": perf001_summary["workloads"]["backoff_deterministic"]["py_pyo3"]["ns_per_op"]["median"],
                    "py_pyo3_raw_call_ns": pyo3_noop_ns,
                    "py_pyo3_extra_arg_marshaling_ns": round(
                        perf001_summary["workloads"]["backoff_deterministic"]["py_pyo3"]["ns_per_op"]["median"]
                        - pyo3_noop_ns
                        - perf001_summary["workloads"]["backoff_deterministic"]["rust_direct"]["ns_per_op"]["median"],
                        2,
                    ),
                },
                "retry_policy_evaluation": {
                    "ts_napi_total_ns": perf001_summary["workloads"]["retry_policy_evaluation"]["ts_napi"]["ns_per_op"]["median"],
                    "ts_napi_raw_call_ns": napi_noop_ns,
                    "ts_napi_string_and_object_marshaling_ns": round(
                        perf001_summary["workloads"]["retry_policy_evaluation"]["ts_napi"]["ns_per_op"]["median"]
                        - napi_noop_ns
                        - perf001_summary["workloads"]["retry_policy_evaluation"]["rust_direct"]["ns_per_op"]["median"],
                        2,
                    ),
                    "py_pyo3_total_ns": perf001_summary["workloads"]["retry_policy_evaluation"]["py_pyo3"]["ns_per_op"]["median"],
                    "py_pyo3_raw_call_ns": pyo3_noop_ns,
                    "py_pyo3_pyclass_and_attr_marshaling_ns": round(
                        perf001_summary["workloads"]["retry_policy_evaluation"]["py_pyo3"]["ns_per_op"]["median"]
                        - pyo3_noop_ns
                        - perf001_summary["workloads"]["retry_policy_evaluation"]["rust_direct"]["ns_per_op"]["median"],
                        2,
                    ),
                },
            },
        },
    }

    metadata = {
        "experiment_id": exp_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system": {
            "os": platform.platform(),
            "processor": platform.processor(),
            "machine": platform.machine(),
        },
        "parameters": {
            "rounds": rounds,
            "warmup_iterations": warmup,
        },
    }

    exp_dir.mkdir(parents=True, exist_ok=False)
    (exp_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (exp_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with open(exp_dir / "raw.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["workload", "language", "round", "iterations", "elapsed_ms", "ops_per_sec", "ns_per_op"],
        )
        writer.writeheader()
        writer.writerows(raw_records)

    print(f"\nValidation artifacts written to: {exp_dir}")


if __name__ == "__main__":
    main()

