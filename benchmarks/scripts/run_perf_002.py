"""Experiment 2 Orchestrator: perf-002-gil-concurrency.

Compares three Python execution modes across 1, 2, 4, and 8 threads:
  1. py_native            : Native Python (executes in CPython while holding the GIL)
  2. py_pyo3_gil_held     : PyO3 calling Rust while holding the GIL
  3. py_pyo3_gil_released : PyO3 calling Rust inside Python::allow_threads (GIL released)

Across three concurrency workloads:
  1. backoff_concurrent   : Stateless backoff calculations across threads
  2. circuit_independent  : Each thread mutates its own independent circuit breaker instance
  3. circuit_shared       : All threads contend on a single shared circuit breaker instance

Outputs immutable artifacts to benchmarks/results/perf-002-gil-concurrency/
and generates benchmarks/research/figures/concurrency.png.
"""

from __future__ import annotations

import csv
import json
import math
import os
import platform
import sys
import threading
import time
import types
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR / "packages" / "smooth-api-py"))

import smoothapi_rs
from smooth_api import state as state_mod
from smooth_api.config import BackoffConfig, CircuitBreakerConfig
from smooth_api.utils import calculate_backoff

RESULTS_DIR = ROOT_DIR / "benchmarks" / "results"
FIGURES_DIR = ROOT_DIR / "benchmarks" / "research" / "figures"

MODES = ["py_native", "py_pyo3_gil_held", "py_pyo3_gil_released"]
THREAD_COUNTS = [1, 2, 4, 8]
WORKLOADS = ["backoff_concurrent", "circuit_independent", "circuit_shared"]

OPS_PER_THREAD = {
    "backoff_concurrent": 400_000,
    "circuit_independent": 250_000,
    "circuit_shared": 250_000,
}


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


def run_backoff_threads(mode: str, num_threads: int, ops_per_thread: int) -> tuple[float, int]:
    batches = ops_per_thread // 5
    actual_ops_per_thread = batches * 5
    total_ops = actual_ops_per_thread * num_threads
    attempts = (0, 1, 2, 3, 10)
    cfg = BackoffConfig(base_delay=0.1, max_delay=30.0, max_retries=3, jitter="none")

    start_ns = [0]
    end_ns = [0] * num_threads

    def record_start() -> None:
        start_ns[0] = time.perf_counter_ns()

    barrier = threading.Barrier(num_threads, action=record_start)

    def worker(tid: int) -> None:
        sink = 0.0
        if mode == "py_native":
            for att in attempts:
                sink += calculate_backoff(att, cfg)
            barrier.wait()
            for _ in range(batches):
                for att in attempts:
                    sink += calculate_backoff(att, cfg)
            end_ns[tid] = time.perf_counter_ns()
        elif mode == "py_pyo3_gil_held":
            fn = smoothapi_rs.calculate_backoff_native
            for att in attempts:
                sink += fn(att, 100, 30000)
            barrier.wait()
            for _ in range(batches):
                for att in attempts:
                    sink += fn(att, 100, 30000)
            end_ns[tid] = time.perf_counter_ns()
        else:
            fn = smoothapi_rs.calculate_backoff_nogil
            for att in attempts:
                sink += fn(att, 100, 30000)
            barrier.wait()
            for _ in range(batches):
                for att in attempts:
                    sink += fn(att, 100, 30000)
            end_ns[tid] = time.perf_counter_ns()
        if sink < 0:
            print(sink)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    wall_ns = max(end_ns) - start_ns[0]
    return wall_ns / 1_000_000.0, total_ops


def run_circuit_threads(
    mode: str, num_threads: int, ops_per_thread: int, shared: bool
) -> tuple[float, int]:
    batches = ops_per_thread // 5
    actual_ops_per_thread = batches * 5
    total_ops = actual_ops_per_thread * num_threads

    start_ns = [0]
    end_ns = [0] * num_threads

    def record_start() -> None:
        start_ns[0] = time.perf_counter_ns()

    barrier = threading.Barrier(num_threads, action=record_start)

    if mode == "py_native":
        shared_cb = (
            state_mod.CircuitBreakerState(
                CircuitBreakerConfig(failure_threshold=3, cooldown_ms=5000)
            )
            if shared
            else None
        )

        def worker_py(tid: int) -> None:
            cb = (
                shared_cb
                if shared
                else state_mod.CircuitBreakerState(
                    CircuitBreakerConfig(failure_threshold=3, cooldown_ms=5000)
                )
            )
            key = "shared.domain" if shared else f"domain.{tid}"
            sink = 0
            barrier.wait()
            for _ in range(batches):
                if cb.can_request(key):
                    sink += 1
                cb.record_failure(key)
                if cb.can_request(key):
                    sink += 1
                cb.record_failure(key)
                if cb.can_request(key):
                    sink += 1
                cb.record_failure(key)
                if not cb.can_request(key):
                    sink += 1
                cb.record_success(key)
            end_ns[tid] = time.perf_counter_ns()
            if sink < 0:
                print(sink)

        threads = [threading.Thread(target=worker_py, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    else:
        shared_native_cb = (
            smoothapi_rs.NativeCircuitBreaker(3, 5000) if shared else None
        )

        def worker_rs(tid: int) -> None:
            cb = shared_native_cb if shared else smoothapi_rs.NativeCircuitBreaker(3, 5000)
            sink = 0
            barrier.wait()
            if mode == "py_pyo3_gil_held":
                for _ in range(batches):
                    if cb.can_request(1000):
                        sink += 1
                    cb.record_failure(1000)
                    if cb.can_request(2000):
                        sink += 1
                    cb.record_failure(2000)
                    if cb.can_request(3000):
                        sink += 1
                    cb.record_failure(3000)
                    if not cb.can_request(5000):
                        sink += 1
                    if cb.can_request(8001):
                        sink += 1
                    cb.record_success()
            else:
                for _ in range(batches):
                    if cb.can_request_nogil(1000):
                        sink += 1
                    cb.record_failure_nogil(1000)
                    if cb.can_request_nogil(2000):
                        sink += 1
                    cb.record_failure_nogil(2000)
                    if cb.can_request_nogil(3000):
                        sink += 1
                    cb.record_failure_nogil(3000)
                    if not cb.can_request_nogil(5000):
                        sink += 1
                    if cb.can_request_nogil(8001):
                        sink += 1
                    cb.record_success_nogil()
            end_ns[tid] = time.perf_counter_ns()
            if sink < 0:
                print(sink)

        threads = [threading.Thread(target=worker_rs, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    wall_ns = max(end_ns) - start_ns[0]
    return wall_ns / 1_000_000.0, total_ops


def generate_concurrency_figure(summary: dict) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    workload_titles = {
        "backoff_concurrent": "1. Stateless Backoff Calculation",
        "circuit_independent": "2. Independent Circuit Breakers (1/Thread)",
        "circuit_shared": "3. Shared Circuit Breaker (Contended)",
    }
    mode_labels = {
        "py_native": "Native Python (GIL Held)",
        "py_pyo3_gil_held": "PyO3 (GIL Held)",
        "py_pyo3_gil_released": "PyO3 (GIL Released: allow_threads)",
    }
    colors = {
        "py_native": "#31a354",
        "py_pyo3_gil_held": "#08519c",
        "py_pyo3_gil_released": "#d95f02",
    }
    markers = {
        "py_native": "o",
        "py_pyo3_gil_held": "s",
        "py_pyo3_gil_released": "^",
    }

    fig, axes = plt.subplots(2, 3, figsize=(16.5, 9.2), dpi=160)
    fig.suptitle(
        "Experiment 2 (perf-002): Python GIL Concurrency Scaling Across 1, 2, 4, and 8 Threads",
        fontsize=13.5,
        fontweight="bold",
        y=1.01,
    )

    # Top row: Aggregate Throughput (Million ops/sec) vs Thread Count
    for col, wl in enumerate(WORKLOADS):
        ax = axes[0, col]
        for mode in MODES:
            ys = [
                summary["workloads"][wl][mode][str(tc)]["ops_per_sec"]["median"] / 1e6
                for tc in THREAD_COUNTS
            ]
            ax.plot(
                THREAD_COUNTS,
                ys,
                marker=markers[mode],
                linewidth=2.2,
                markersize=7,
                color=colors[mode],
                label=mode_labels[mode],
            )
            for tc, y in zip(THREAD_COUNTS, ys):
                ax.annotate(
                    f"{y:.2f}M",
                    (tc, y),
                    textcoords="offset points",
                    xytext=(0, 6),
                    ha="center",
                    fontsize=8,
                )
        ax.set_title(f"{workload_titles[wl]}\nAggregate Throughput (Higher is Better)", fontsize=10.5, fontweight="bold")
        ax.set_xticks(THREAD_COUNTS)
        ax.set_xlabel("Thread Count")
        if col == 0:
            ax.set_ylabel("Aggregate Throughput (Million ops/sec)")
        ax.grid(True, linestyle="--", alpha=0.4)
        if col == 0:
            ax.legend(loc="best", fontsize=8.5, frameon=True)

    # Bottom row: Effective Wall-Clock Latency (ns/op) vs Thread Count
    for col, wl in enumerate(WORKLOADS):
        ax = axes[1, col]
        for mode in MODES:
            ys = [
                summary["workloads"][wl][mode][str(tc)]["effective_ns_per_op"]["median"]
                for tc in THREAD_COUNTS
            ]
            ax.plot(
                THREAD_COUNTS,
                ys,
                marker=markers[mode],
                linewidth=2.2,
                markersize=7,
                color=colors[mode],
                label=mode_labels[mode],
            )
            for tc, y in zip(THREAD_COUNTS, ys):
                ax.annotate(
                    f"{y:.0f}ns",
                    (tc, y),
                    textcoords="offset points",
                    xytext=(0, 6),
                    ha="center",
                    fontsize=8,
                )
        ax.set_title(f"{workload_titles[wl]}\nEffective Wall-Clock Latency (Lower is Better)", fontsize=10.5, fontweight="bold")
        ax.set_xticks(THREAD_COUNTS)
        ax.set_xlabel("Thread Count")
        if col == 0:
            ax.set_ylabel("Effective Wall-Clock Latency (ns / op)")
        ax.grid(True, linestyle="--", alpha=0.4)

    fig.tight_layout()
    out_path = FIGURES_DIR / "exp-003-concurrency.png"
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return str(out_path)


def main() -> None:
    exp_id = "perf-002-gil-concurrency"
    exp_dir = RESULTS_DIR / exp_id
    if exp_dir.exists():
        print(f"ERROR: {exp_dir} already exists!", file=sys.stderr)
        sys.exit(1)

    rounds = 5
    raw_records = []

    print("=" * 85)
    print(f" SmoothAPI GIL & Concurrency Benchmark - {exp_id}")
    print(f" Modes: {', '.join(MODES)} | Threads: {THREAD_COUNTS} | Rounds: {rounds}")
    print("=" * 85)

    for wl in WORKLOADS:
        ops_per_thread = OPS_PER_THREAD[wl]
        print(f"\n>> Workload: {wl} ({ops_per_thread:,} ops/thread)")
        for tc in THREAD_COUNTS:
            print(f"  -- Threads: {tc} --")
            for r in range(1, rounds + 1):
                order = MODES[(r - 1) % len(MODES) :] + MODES[: (r - 1) % len(MODES)]
                for mode in order:
                    if wl == "backoff_concurrent":
                        elapsed_ms, total_ops = run_backoff_threads(mode, tc, ops_per_thread)
                    elif wl == "circuit_independent":
                        elapsed_ms, total_ops = run_circuit_threads(mode, tc, ops_per_thread, shared=False)
                    else:
                        elapsed_ms, total_ops = run_circuit_threads(mode, tc, ops_per_thread, shared=True)

                    ops_per_sec = total_ops / (elapsed_ms / 1000.0)
                    effective_ns_per_op = (elapsed_ms * 1_000_000.0) / total_ops
                    thread_latency_ns = effective_ns_per_op * tc

                    rec = {
                        "workload": wl,
                        "mode": mode,
                        "threads": tc,
                        "round": r,
                        "total_ops": total_ops,
                        "elapsed_ms": round(elapsed_ms, 4),
                        "ops_per_sec": round(ops_per_sec, 2),
                        "effective_ns_per_op": round(effective_ns_per_op, 4),
                        "per_thread_latency_ns": round(thread_latency_ns, 4),
                    }
                    raw_records.append(rec)
                if r == rounds:
                    for mode in MODES:
                        m_recs = [
                            x for x in raw_records
                            if x["workload"] == wl and x["mode"] == mode and x["threads"] == tc
                        ]
                        med_ops = calculate_stats([x["ops_per_sec"] for x in m_recs])["median"]
                        med_ns = calculate_stats([x["effective_ns_per_op"] for x in m_recs])["median"]
                        print(
                            f"    [{mode:<22}] median: {med_ops:>12,.0f} ops/sec | "
                            f"{med_ns:>7.2f} effective ns/op"
                        )

    summary: dict = {"experiment_id": exp_id, "workloads": {}}
    for wl in WORKLOADS:
        summary["workloads"][wl] = {}
        for mode in MODES:
            summary["workloads"][wl][mode] = {}
            for tc in THREAD_COUNTS:
                recs = [
                    x for x in raw_records
                    if x["workload"] == wl and x["mode"] == mode and x["threads"] == tc
                ]
                summary["workloads"][wl][mode][str(tc)] = {
                    "total_ops": recs[0]["total_ops"],
                    "ops_per_sec": calculate_stats([x["ops_per_sec"] for x in recs]),
                    "effective_ns_per_op": calculate_stats([x["effective_ns_per_op"] for x in recs]),
                    "per_thread_latency_ns": calculate_stats([x["per_thread_latency_ns"] for x in recs]),
                    "elapsed_ms": calculate_stats([x["elapsed_ms"] for x in recs]),
                }

    metadata = {
        "experiment_id": exp_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system": {
            "os": platform.platform(),
            "processor": platform.processor(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
            "python": sys.version.split()[0],
        },
        "parameters": {
            "rounds": rounds,
            "modes": MODES,
            "thread_counts": THREAD_COUNTS,
            "ops_per_thread": OPS_PER_THREAD,
        },
    }

    exp_dir.mkdir(parents=True, exist_ok=False)
    (exp_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (exp_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    with open(exp_dir / "raw.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "workload",
                "mode",
                "threads",
                "round",
                "total_ops",
                "elapsed_ms",
                "ops_per_sec",
                "effective_ns_per_op",
                "per_thread_latency_ns",
            ],
        )
        writer.writeheader()
        writer.writerows(raw_records)

    fig_path = generate_concurrency_figure(summary)
    print(f"\nGenerated figure: {fig_path}")
    print(f"Artifacts written to: {exp_dir}")


if __name__ == "__main__":
    main()

