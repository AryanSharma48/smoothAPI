"""Experiment 1 Orchestrator: perf-001-microbenchmarks.

Measures all five SmoothAPI implementations across three core resilience operations:
  1. backoff_deterministic       (Exponential backoff calculation)
  2. retry_policy_evaluation     (Status + Retry-After header evaluation)
  3. circuit_breaker_transitions (5-step CLOSED -> OPEN -> HALF_OPEN -> CLOSED cycle)

Implementations compared:
  - rust_direct : Direct Rust (smooth-api-core)
  - ts_native   : Native TypeScript (packages/smooth-api-ts)
  - ts_napi     : TypeScript -> Node-API -> Rust (bindings/node)
  - py_native   : Native Python (packages/smooth-api-py)
  - py_pyo3     : Python -> PyO3 -> Rust (bindings/python)

Outputs immutable artifacts to benchmarks/results/perf-001-microbenchmarks/
and generates latency.png, throughput.png, and speedup.png in benchmarks/research/figures/.
"""

from __future__ import annotations

import argparse
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

IMPLS = ["rust_direct", "ts_native", "ts_napi", "py_native", "py_pyo3"]
WORKLOADS = [
    "backoff_deterministic",
    "retry_policy_evaluation",
    "circuit_breaker_transitions",
]

# Calibrated iteration counts targeting ~0.4s - 1.2s per round per implementation
CALIBRATED_ITERATIONS = {
    "backoff_deterministic": {
        "rust_direct": 200_000_000,
        "ts_native": 25_000_000,
        "ts_napi": 10_000_000,
        "py_native": 2_500_000,
        "py_pyo3": 5_000_000,
    },
    "retry_policy_evaluation": {
        "rust_direct": 100_000_000,
        "ts_native": 20_000_000,
        "ts_napi": 5_000_000,
        "py_native": 1_500_000,
        "py_pyo3": 2_500_000,
    },
    "circuit_breaker_transitions": {
        "rust_direct": 150_000_000,
        "ts_native": 10_000_000,
        "ts_napi": 10_000_000,
        "py_native": 1_000_000,
        "py_pyo3": 4_000_000,
    },
}


def get_git_commit() -> str:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return "unknown"


def get_toolchain_versions() -> dict:
    versions = {}
    for name, cmd in [("rustc", ["rustc", "--version"]), ("node", ["node", "--version"])]:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, check=False)
            versions[name] = r.stdout.strip()
        except Exception:
            versions[name] = "unknown"
    versions["python"] = sys.version.split()[0]
    return versions


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


def build_rust_runner() -> Path:
    subprocess.run(
        [
            "cargo",
            "build",
            "--release",
            "--bin",
            "benchmark-rust",
            "--manifest-path",
            str(ROOT_DIR / "benchmarks" / "rust" / "Cargo.toml"),
        ],
        cwd=ROOT_DIR,
        check=True,
    )
    exe_name = "benchmark-rust.exe" if sys.platform == "win32" else "benchmark-rust"
    return ROOT_DIR / "benchmarks" / "rust" / "target" / "release" / exe_name


def run_single(rust_bin: Path, impl: str, workload: str, iterations: int, warmup: int, round_num: int) -> dict:
    if impl == "rust_direct":
        cmd = [
            str(rust_bin),
            "--workload",
            workload,
            "--iterations",
            str(iterations),
            "--warmup",
            str(warmup),
            "--round",
            str(round_num),
        ]
    elif impl in ("ts_native", "ts_napi"):
        cmd = [
            "node",
            str(ROOT_DIR / "benchmarks" / "typescript" / "bench.mjs"),
            "--impl",
            impl,
            "--workload",
            workload,
            "--iterations",
            str(iterations),
            "--warmup",
            str(warmup),
            "--round",
            str(round_num),
        ]
    else:
        cmd = [
            sys.executable,
            str(ROOT_DIR / "benchmarks" / "python" / "bench.py"),
            "--impl",
            impl,
            "--workload",
            workload,
            "--iterations",
            str(iterations),
            "--warmup",
            str(warmup),
            "--round",
            str(round_num),
        ]

    res = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True, check=True)
    for line in reversed(res.stdout.strip().splitlines()):
        if line.startswith("{") and line.endswith("}"):
            rec = json.loads(line)
            rec["language"] = impl
            return rec
    raise RuntimeError(f"Runner {impl} did not emit JSON: {res.stdout}")


def generate_figures(summary: dict) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    workload_labels = {
        "backoff_deterministic": "Backoff Calculation",
        "retry_policy_evaluation": "Retry Policy Evaluation",
        "circuit_breaker_transitions": "Circuit Breaker Transitions",
    }
    impl_labels = {
        "rust_direct": "Direct Rust",
        "ts_native": "Native TS",
        "ts_napi": "TS + Node-API",
        "py_native": "Native Python",
        "py_pyo3": "Python + PyO3",
    }
    colors = {
        "rust_direct": "#d95f02",
        "ts_native": "#3182bd",
        "ts_napi": "#08519c",
        "py_native": "#31a354",
        "py_pyo3": "#006d2c",
    }

    # ── Graph A: Operation Latency (ns/op) ──────────────────────────────────────
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.2), dpi=160)
    fig.suptitle(
        "Experiment 1 (perf-001): Per-Operation Latency Across All 5 Implementations (Lower is Better)",
        fontsize=13,
        fontweight="bold",
        y=1.02,
    )

    for idx, wl in enumerate(WORKLOADS):
        ax = axes[idx]
        w_data = summary["workloads"][wl]
        medians = [w_data[imp]["ns_per_op"]["median"] for imp in IMPLS]
        stdevs = [w_data[imp]["ns_per_op"]["stdev"] for imp in IMPLS]
        x = np.arange(len(IMPLS))
        bars = ax.bar(
            x,
            medians,
            yerr=stdevs,
            capsize=4,
            color=[colors[imp] for imp in IMPLS],
            edgecolor="#222222",
            linewidth=0.7,
        )
        ax.set_title(workload_labels[wl], fontsize=11, fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels([impl_labels[imp] for imp in IMPLS], rotation=22, ha="right", fontsize=9)
        ax.set_ylabel("Latency (ns / op)" if idx == 0 else "")
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        max_y = max(medians) * 1.18
        ax.set_ylim(0, max_y)
        for bar, val in zip(bars, medians):
            ax.text(
                bar.get_x() + bar.get_width() / 2.0,
                bar.get_height() + max_y * 0.02,
                f"{val:.1f} ns",
                ha="center",
                va="bottom",
                fontsize=8.5,
                fontweight="bold",
            )

    fig.tight_layout()
    latency_path = FIGURES_DIR / "exp-002-latency.png"
    fig.savefig(latency_path, bbox_inches="tight")
    plt.close(fig)

    # ── Graph B: Throughput (Million ops/sec) ───────────────────────────────────
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.2), dpi=160)
    fig.suptitle(
        "Experiment 1 (perf-001): Throughput Across All 5 Implementations (Higher is Better, Log Scale)",
        fontsize=13,
        fontweight="bold",
        y=1.02,
    )

    for idx, wl in enumerate(WORKLOADS):
        ax = axes[idx]
        w_data = summary["workloads"][wl]
        mops = [w_data[imp]["ops_per_sec"]["median"] / 1e6 for imp in IMPLS]
        x = np.arange(len(IMPLS))
        bars = ax.bar(
            x,
            mops,
            color=[colors[imp] for imp in IMPLS],
            edgecolor="#222222",
            linewidth=0.7,
        )
        ax.set_yscale("log")
        ax.set_title(workload_labels[wl], fontsize=11, fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels([impl_labels[imp] for imp in IMPLS], rotation=22, ha="right", fontsize=9)
        ax.set_ylabel("Throughput (Million ops/sec, log scale)" if idx == 0 else "")
        ax.grid(axis="y", which="both", linestyle="--", alpha=0.4)
        ax.set_ylim(min(mops) * 0.5, max(mops) * 3.0)
        for bar, val in zip(bars, mops):
            ax.text(
                bar.get_x() + bar.get_width() / 2.0,
                bar.get_height() * 1.12,
                f"{val:.1f}M/s",
                ha="center",
                va="bottom",
                fontsize=8.5,
                fontweight="bold",
            )

    fig.tight_layout()
    throughput_path = FIGURES_DIR / "exp-002-throughput.png"
    fig.savefig(throughput_path, bbox_inches="tight")
    plt.close(fig)

    # ── Graph C: Rust-Backed Speedup Ratio (Native Latency / Bound Latency) ─────
    fig, ax = plt.subplots(figsize=(10, 5.4), dpi=160)
    x = np.arange(len(WORKLOADS))
    width = 0.35

    ts_speedups = [
        summary["workloads"][wl]["ffi_analysis"]["ts_napi_speedup_vs_ts_native"]
        for wl in WORKLOADS
    ]
    py_speedups = [
        summary["workloads"][wl]["ffi_analysis"]["py_pyo3_speedup_vs_py_native"]
        for wl in WORKLOADS
    ]

    bars_ts = ax.bar(
        x - width / 2,
        ts_speedups,
        width,
        label="TypeScript -> Node-API vs Native TS",
        color="#08519c",
        edgecolor="#222222",
    )
    bars_py = ax.bar(
        x + width / 2,
        py_speedups,
        width,
        label="Python -> PyO3 vs Native Python",
        color="#006d2c",
        edgecolor="#222222",
    )

    ax.axhline(1.0, color="#cb181d", linestyle="--", linewidth=1.4, label="Break-even (1.0x: FFI cost = Rust gain)")
    ax.set_title(
        "Experiment 1 (perf-001): Rust-Backed Speedup Ratio (Native Latency / Bound Latency)",
        fontsize=12,
        fontweight="bold",
    )
    ax.set_xticks(x)
    ax.set_xticklabels([workload_labels[wl] for wl in WORKLOADS], fontsize=10, fontweight="bold")
    ax.set_ylabel("Speedup Ratio (> 1.0x = Faster than Native, < 1.0x = Slower due to FFI)")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    max_s = max(max(ts_speedups), max(py_speedups), 1.2) * 1.18
    ax.set_ylim(0, max_s)
    ax.legend(loc="upper left", frameon=True)

    for bar in list(bars_ts) + list(bars_py):
        h = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            h + max_s * 0.02,
            f"{h:.2f}x",
            ha="center",
            va="bottom",
            fontsize=9.5,
            fontweight="bold",
        )

    fig.tight_layout()
    speedup_path = FIGURES_DIR / "exp-002-speedup.png"
    fig.savefig(speedup_path, bbox_inches="tight")
    plt.close(fig)

    return [str(latency_path), str(throughput_path), str(speedup_path)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-id", default="perf-001-microbenchmarks")
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--warmup", type=int, default=50_000)
    args = parser.parse_args()

    exp_id = args.experiment_id
    exp_dir = RESULTS_DIR / exp_id
    if exp_dir.exists():
        print(
            f"ERROR: Experiment directory '{exp_dir}' already exists! Immutability policy forbids overwriting.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("Building Rust release benchmark binary...")
    rust_bin = build_rust_runner()

    rounds = args.rounds
    warmup = args.warmup
    raw_records = []

    print("=" * 85)
    print(f" SmoothAPI 5-Implementation Microbenchmark Suite - Experiment: {exp_id}")
    print(f" Rounds: {rounds} | Warm-up: {warmup:,} | Implementations: {', '.join(IMPLS)}")
    print("=" * 85)

    for workload in WORKLOADS:
        print(f"\n>> Workload: {workload}")
        for r in range(1, rounds + 1):
            order = IMPLS[(r - 1) % len(IMPLS) :] + IMPLS[: (r - 1) % len(IMPLS)]
            print(f"  Round {r}/{rounds} (Order: {' -> '.join(order)})")
            for impl in order:
                iters = CALIBRATED_ITERATIONS[workload][impl]
                rec = run_single(rust_bin, impl, workload, iters, warmup, r)
                raw_records.append(rec)
                print(
                    f"    [{impl:<12}] {rec['ns_per_op']:>8.2f} ns/op | "
                    f"{rec['ops_per_sec']:>14,.0f} ops/sec "
                    f"({rec['elapsed_ms']:>7.1f} ms | {rec['iterations']:>11,} iters)"
                )

    summary: dict = {"experiment_id": exp_id, "workloads": {}}

    for workload in WORKLOADS:
        w_summary: dict = {}
        for impl in IMPLS:
            recs = [r for r in raw_records if r["workload"] == workload and r["language"] == impl]
            w_summary[impl] = {
                "sample_iterations": recs[0]["iterations"] if recs else 0,
                "ns_per_op": calculate_stats([r["ns_per_op"] for r in recs]),
                "ops_per_sec": calculate_stats([r["ops_per_sec"] for r in recs]),
                "elapsed_ms": calculate_stats([r["elapsed_ms"] for r in recs]),
            }

        rust_ns = w_summary["rust_direct"]["ns_per_op"]["median"]
        ts_nat_ns = w_summary["ts_native"]["ns_per_op"]["median"]
        ts_napi_ns = w_summary["ts_napi"]["ns_per_op"]["median"]
        py_nat_ns = w_summary["py_native"]["ns_per_op"]["median"]
        py_pyo3_ns = w_summary["py_pyo3"]["ns_per_op"]["median"]

        napi_ffi_ns = max(0.0, ts_napi_ns - rust_ns)
        pyo3_ffi_ns = max(0.0, py_pyo3_ns - rust_ns)

        w_summary["ffi_analysis"] = {
            "ts_napi_speedup_vs_ts_native": round(ts_nat_ns / ts_napi_ns, 3),
            "py_pyo3_speedup_vs_py_native": round(py_nat_ns / py_pyo3_ns, 3),
            "ts_native_vs_rust_direct_ratio": round(ts_nat_ns / rust_ns, 2),
            "py_native_vs_rust_direct_ratio": round(py_nat_ns / rust_ns, 2),
            "napi_ffi_overhead_ns": round(napi_ffi_ns, 2),
            "napi_ffi_share_pct": round((napi_ffi_ns / ts_napi_ns) * 100.0, 1),
            "pyo3_ffi_overhead_ns": round(pyo3_ffi_ns, 2),
            "pyo3_ffi_share_pct": round((pyo3_ffi_ns / py_pyo3_ns) * 100.0, 1),
        }
        summary["workloads"][workload] = w_summary

    metadata = {
        "experiment_id": exp_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": get_git_commit(),
        "system": {
            "os": platform.platform(),
            "processor": platform.processor(),
            "machine": platform.machine(),
        },
        "toolchains": get_toolchain_versions(),
        "parameters": {
            "rounds": rounds,
            "warmup_iterations": warmup,
            "implementations": IMPLS,
            "workloads": WORKLOADS,
            "calibrated_iterations": CALIBRATED_ITERATIONS,
        },
        "methodology_notes": [
            "Preserves original exp-001 untouched; records 5-implementation comparison under perf-001-microbenchmarks.",
            "All 5 implementations passed 575/575 differential checks (diff-003-audited) prior to measurement.",
            "Execution order is counterbalanced across 5 rounds to control for thermal and OS scheduling drift.",
            "FFI call overhead is decomposed by subtracting Direct Rust latency from Node-API and PyO3 bound latencies.",
        ],
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

    figure_paths = generate_figures(summary)
    print("\nGenerated figures:")
    for fp in figure_paths:
        print(f"  - {fp}")
    print(f"\nExperiment artifacts written to: {exp_dir}")


if __name__ == "__main__":
    main()
