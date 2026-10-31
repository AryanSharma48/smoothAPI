"""Orchestrator for Experiment 3b (perf-003b-fair-fast-fail): Fair Circuit-Breaker Fast-Fail Benchmark.

Isolates the circuit-breaker implementation under identical client execution paths for `repeated_failures_cb`:
  - Both ts_native and ts_napi execute identical URL parsing (`new URL()`), circuit-key resolution
    (`getCircuitKey()`), JS `Map` lookup (`getOrCreate(domain)`), lifecycle hook checks, and fallback return.
  - Both py_native and py_pyo3 execute identical URL extraction (`_extract_url`), `urlparse`-based circuit-key
    resolution (`_resolve_circuit_key`), Python `dict` + `RLock` lookup, lifecycle hook checks, and fallback return.
  - Only the underlying per-domain circuit-breaker state transition / check (`CircuitBreakerState` vs
    `NativeCircuitBreaker`) differs.

Preserves `benchmarks/results/perf-003-end-to-end/` untouched and writes:
  - benchmarks/results/perf-003b-fair-fast-fail/raw.csv
  - benchmarks/results/perf-003b-fair-fast-fail/metadata.json
  - benchmarks/results/perf-003b-fair-fast-fail/summary.json
  - benchmarks/research/figures/exp-004b-fair-fast-fail.png
"""

from __future__ import annotations

import csv
import datetime
import json
import math
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT_DIR / "benchmarks" / "results" / "perf-003b-fair-fast-fail"
PERF_003_SUMMARY = ROOT_DIR / "benchmarks" / "results" / "perf-003-end-to-end" / "summary.json"
FIGURES_DIR = ROOT_DIR / "benchmarks" / "research" / "figures"

PORT = 3099
BASE_URL = f"http://127.0.0.1:{PORT}"
ROUNDS = 5
SCENARIO = "repeated_failures_cb"
REQUESTS = 10000
WARMUP = 20

IMPLEMENTATIONS = [
    ("ts_native", "Native TypeScript"),
    ("ts_napi", "TypeScript + Node-API (Rust, Fair Path)"),
    ("py_native", "Native Python"),
    ("py_pyo3", "Python + PyO3 (Rust, Fair Path)"),
]


def start_server() -> subprocess.Popen:
    server_script = ROOT_DIR / "benchmarks" / "scripts" / "e2e_server.mjs"
    proc = subprocess.Popen(
        ["node", str(server_script), str(PORT)],
        cwd=str(ROOT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.time() + 10.0
    while time.time() < deadline:
        line = proc.stdout.readline() if proc.stdout else ""
        if f"E2E_SERVER_READY:{PORT}" in line:
            return proc
        if proc.poll() is not None:
            err = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(f"E2E server exited prematurely: {err}")
    proc.terminate()
    raise RuntimeError("Timed out waiting for E2E HTTP server to start")


def run_single(impl: str, round_num: int) -> dict:
    if impl.startswith("ts_"):
        script = ROOT_DIR / "benchmarks" / "typescript" / "bench_e2e.mjs"
        cmd = [
            "node",
            str(script),
            "--impl",
            impl,
            "--scenario",
            SCENARIO,
            "--url",
            BASE_URL,
            "--requests",
            str(REQUESTS),
            "--warmup",
            str(WARMUP),
            "--round",
            str(round_num),
            "--fair",
        ]
    else:
        script = ROOT_DIR / "benchmarks" / "python" / "bench_e2e.py"
        cmd = [
            sys.executable,
            str(script),
            "--impl",
            impl,
            "--scenario",
            SCENARIO,
            "--url",
            BASE_URL,
            "--requests",
            str(REQUESTS),
            "--warmup",
            str(WARMUP),
            "--round",
            str(round_num),
            "--fair",
        ]

    res = subprocess.run(cmd, cwd=str(ROOT_DIR), capture_output=True, text=True, check=True)
    for line in reversed(res.stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            return json.loads(line)
    raise RuntimeError(f"Failed to parse JSON output from {cmd}: {res.stdout}")


def aggregate_summary(raw_rows: list[dict]) -> dict:
    metrics = [
        "req_per_sec",
        "mean_ms",
        "p50_ms",
        "p95_ms",
        "p99_ms",
        "cpu_ms_per_1k_reqs",
        "cpu_pct",
        "rss_mb",
        "heap_mb",
    ]
    sc_summary: dict = {}
    for impl_id, impl_label in IMPLEMENTATIONS:
        rows = [r for r in raw_rows if r["impl"] == impl_id]
        entry: dict = {"label": impl_label, "rounds": len(rows)}
        for m in metrics:
            vals = [float(r[m]) for r in rows]
            mean_v = statistics.mean(vals)
            sd_v = statistics.stdev(vals) if len(vals) > 1 else 0.0
            ci95_v = 1.96 * sd_v / math.sqrt(len(vals)) if len(vals) > 1 else 0.0
            entry[m] = {
                "mean": round(mean_v, 4),
                "median": round(statistics.median(vals), 4),
                "sd": round(sd_v, 4),
                "ci95": round(ci95_v, 4),
                "min": round(min(vals), 4),
                "max": round(max(vals), 4),
            }
        sc_summary[impl_id] = entry

    ts_nat_rps = sc_summary["ts_native"]["req_per_sec"]["mean"]
    ts_napi_rps = sc_summary["ts_napi"]["req_per_sec"]["mean"]
    py_nat_rps = sc_summary["py_native"]["req_per_sec"]["mean"]
    py_pyo3_rps = sc_summary["py_pyo3"]["req_per_sec"]["mean"]

    ts_nat_cpu = sc_summary["ts_native"]["cpu_ms_per_1k_reqs"]["mean"]
    ts_napi_cpu = sc_summary["ts_napi"]["cpu_ms_per_1k_reqs"]["mean"]
    py_nat_cpu = sc_summary["py_native"]["cpu_ms_per_1k_reqs"]["mean"]
    py_pyo3_cpu = sc_summary["py_pyo3"]["cpu_ms_per_1k_reqs"]["mean"]

    comparison_with_perf_003 = {}
    if PERF_003_SUMMARY.exists():
        p003 = json.loads(PERF_003_SUMMARY.read_text(encoding="utf-8"))
        comparison_with_perf_003 = {
            "perf_003_unequal_prework": p003["relative_speedups"]["repeated_failures_cb"],
            "perf_003b_equal_prework": {
                "ts_napi_vs_ts_native_rps_ratio": round(ts_napi_rps / ts_nat_rps, 4),
                "py_pyo3_vs_py_native_rps_ratio": round(py_pyo3_rps / py_nat_rps, 4),
                "ts_napi_vs_ts_native_cpu_reduction": round(ts_nat_cpu / ts_napi_cpu, 4) if ts_napi_cpu > 0 else 1.0,
                "py_pyo3_vs_py_native_cpu_reduction": round(py_nat_cpu / py_pyo3_cpu, 4) if py_pyo3_cpu > 0 else 1.0,
            },
        }

    return {
        "scenario": SCENARIO,
        "implementations": sc_summary,
        "relative_speedups": {
            "ts_napi_vs_ts_native_rps_ratio": round(ts_napi_rps / ts_nat_rps, 4),
            "py_pyo3_vs_py_native_rps_ratio": round(py_pyo3_rps / py_nat_rps, 4),
            "ts_native_vs_py_native_rps_ratio": round(ts_nat_rps / py_nat_rps, 4),
            "ts_napi_vs_ts_native_cpu_reduction": round(ts_nat_cpu / ts_napi_cpu, 4) if ts_napi_cpu > 0 else 1.0,
            "py_pyo3_vs_py_native_cpu_reduction": round(py_nat_cpu / py_pyo3_cpu, 4) if py_pyo3_cpu > 0 else 1.0,
        },
        "comparison_with_perf_003": comparison_with_perf_003,
    }


def generate_figure(summary: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({
        "font.sans-serif": "DejaVu Sans",
        "axes.edgecolor": "#334155",
        "axes.linewidth": 0.9,
    })

    p003 = json.loads(PERF_003_SUMMARY.read_text(encoding="utf-8"))
    p003_cb = p003["scenarios"]["repeated_failures_cb"]
    p003b_cb = summary["implementations"]

    fig, axes = plt.subplots(1, 3, figsize=(15.5, 5.2), dpi=180)
    fig.suptitle(
        "Experiment 3b (perf-003b): Circuit-Breaker Fast-Fail — Unmatched Pre-Work (perf-003) vs Fair Equal Path (perf-003b)",
        fontsize=12,
        fontweight="bold",
        y=0.98,
    )

    impl_keys = ["ts_native", "ts_napi", "py_native", "py_pyo3"]
    short_labels = ["TS\nNative", "TS +\nNode-API", "Python\nNative", "Python +\nPyO3"]
    x = np.arange(len(impl_keys))
    w = 0.35

    # Panel 1: Throughput (req/s)
    ax0 = axes[0]
    rps_003 = [p003_cb[k]["req_per_sec"]["mean"] / 1000.0 for k in impl_keys]
    rps_003b = [p003b_cb[k]["req_per_sec"]["mean"] / 1000.0 for k in impl_keys]
    b1 = ax0.bar(x - w / 2, rps_003, width=w, label="perf-003 (Direct Native Wrapper)", color="#94a3b8", edgecolor="#0f172a")
    b2 = ax0.bar(x + w / 2, rps_003b, width=w, label="perf-003b (Fair Equal Pre-Work)", color="#0284c7", edgecolor="#0f172a")
    ax0.set_title("Fast-Fail Throughput (k req/sec)", fontsize=10.5, fontweight="bold")
    ax0.set_xticks(x)
    ax0.set_xticklabels(short_labels, fontsize=9)
    ax0.set_ylabel("Thousand Requests / sec (Higher is better)")
    ax0.grid(axis="y", linestyle="--", alpha=0.35)
    max_rps = max(max(rps_003), max(rps_003b))
    ax0.set_ylim(0, max_rps * 1.22)
    for bar, v in zip(list(b1) + list(b2), rps_003 + rps_003b):
        ax0.text(
            bar.get_x() + bar.get_width() / 2.0,
            bar.get_height() + max_rps * 0.02,
            f"{v:.0f}k",
            ha="center",
            va="bottom",
            fontsize=8,
            fontweight="bold",
        )
    ax0.legend(loc="upper left", fontsize=8.5, frameon=True)

    # Panel 2: P50 & P99 Latency (microseconds)
    ax1 = axes[1]
    p50_us = [p003b_cb[k]["p50_ms"]["mean"] * 1000.0 for k in impl_keys]
    p95_us = [p003b_cb[k]["p95_ms"]["mean"] * 1000.0 for k in impl_keys]
    p99_us = [p003b_cb[k]["p99_ms"]["mean"] * 1000.0 for k in impl_keys]
    w3 = 0.25
    bp50 = ax1.bar(x - w3, p50_us, width=w3, label="P50 (µs)", color="#10b981", edgecolor="#0f172a")
    bp95 = ax1.bar(x, p95_us, width=w3, label="P95 (µs)", color="#f59e0b", edgecolor="#0f172a")
    bp99 = ax1.bar(x + w3, p99_us, width=w3, label="P99 (µs)", color="#ef4444", edgecolor="#0f172a")
    ax1.set_title("Fair Fast-Fail Latency Percentiles (µs)", fontsize=10.5, fontweight="bold")
    ax1.set_xticks(x)
    ax1.set_xticklabels(short_labels, fontsize=9)
    ax1.set_ylabel("Latency in µs (Lower is better)")
    ax1.grid(axis="y", linestyle="--", alpha=0.35)
    max_us = max(p99_us)
    ax1.set_ylim(0, max_us * 1.25)
    for bar, v in zip(list(bp50) + list(bp95) + list(bp99), p50_us + p95_us + p99_us):
        ax1.text(
            bar.get_x() + bar.get_width() / 2.0,
            bar.get_height() + max_us * 0.02,
            f"{v:.1f}",
            ha="center",
            va="bottom",
            fontsize=7.5,
        )
    ax1.legend(loc="upper left", fontsize=8.5, frameon=True)

    # Panel 3: Speedup Ratio Comparison (perf-003 vs perf-003b)
    ax2 = axes[2]
    cats = ["TS: Node-API\nvs Native TS", "Python: PyO3\nvs Native Python"]
    x2 = np.arange(len(cats))
    r_003 = [
        p003["relative_speedups"]["repeated_failures_cb"]["ts_napi_vs_ts_native_rps_ratio"],
        p003["relative_speedups"]["repeated_failures_cb"]["py_pyo3_vs_py_native_rps_ratio"],
    ]
    r_003b = [
        summary["relative_speedups"]["ts_napi_vs_ts_native_rps_ratio"],
        summary["relative_speedups"]["py_pyo3_vs_py_native_rps_ratio"],
    ]
    br1 = ax2.bar(x2 - w / 2, r_003, width=w, label="perf-003 (Unmatched Pre-Work)", color="#94a3b8", edgecolor="#0f172a")
    br2 = ax2.bar(x2 + w / 2, r_003b, width=w, label="perf-003b (Fair Equal Pre-Work)", color="#10b981", edgecolor="#0f172a")
    ax2.axhline(1.0, color="#ef4444", linestyle="--", linewidth=1.2, label="Parity (1.00x)")
    ax2.set_title("Rust-Backed Speedup Ratio (RPS)", fontsize=10.5, fontweight="bold")
    ax2.set_xticks(x2)
    ax2.set_xticklabels(cats, fontsize=9.5)
    ax2.set_ylabel("Speedup Ratio (>1.0x = Rust Faster)")
    ax2.grid(axis="y", linestyle="--", alpha=0.35)
    max_r = max(max(r_003), max(r_003b))
    ax2.set_ylim(0, max_r * 1.22)
    for bar, v in zip(list(br1) + list(br2), r_003 + r_003b):
        ax2.text(
            bar.get_x() + bar.get_width() / 2.0,
            bar.get_height() + max_r * 0.02,
            f"{v:.2f}x",
            ha="center",
            va="bottom",
            fontsize=8.5,
            fontweight="bold",
        )
    ax2.legend(loc="upper left", fontsize=8.5, frameon=True)

    fig.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(FIGURES_DIR / "exp-004b-fair-fast-fail.png")
    plt.close(fig)


def main() -> None:
    if RESULTS_DIR.exists():
        print(f"ERROR: {RESULTS_DIR} already exists! Immutability policy forbids overwriting.", file=sys.stderr)
        sys.exit(1)

    RESULTS_DIR.mkdir(parents=True, exist_ok=False)
    server_proc = start_server()
    print(f"[perf-003b] Controlled HTTP server listening on {BASE_URL}")

    raw_rows: list[dict] = []
    try:
        for r in range(1, ROUNDS + 1):
            shift = (r - 1) % len(IMPLEMENTATIONS)
            ordered_impls = IMPLEMENTATIONS[shift:] + IMPLEMENTATIONS[:shift]
            for impl_id, _ in ordered_impls:
                row = run_single(impl=impl_id, round_num=r)
                raw_rows.append(row)
                print(
                    f"  [Round {r}/{ROUNDS}] {SCENARIO:<22} | {impl_id:<10} | "
                    f"{row['req_per_sec']:>10.2f} req/s | "
                    f"P50={row['p50_ms']:.4f}ms P95={row['p95_ms']:.4f}ms P99={row['p99_ms']:.4f}ms | "
                    f"CPU/1k={row['cpu_ms_per_1k_reqs']:.2f}ms | RSS={row['rss_mb']:.1f}MB"
                )
    finally:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except Exception:
            server_proc.kill()

    fieldnames = [
        "scenario",
        "impl",
        "round",
        "requests",
        "elapsed_ms",
        "req_per_sec",
        "mean_ms",
        "p50_ms",
        "p95_ms",
        "p99_ms",
        "cpu_ms",
        "cpu_ms_per_1k_reqs",
        "cpu_pct",
        "rss_mb",
        "heap_mb",
    ]
    with (RESULTS_DIR / "raw.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(raw_rows)

    summary = aggregate_summary(raw_rows)
    (RESULTS_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    node_ver = subprocess.run(
        ["node", "--version"], capture_output=True, text=True, check=False
    ).stdout.strip()
    metadata = {
        "experiment_id": "perf-003b-fair-fast-fail",
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "os": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python_version": sys.version,
        "node_version": node_ver,
        "rounds": ROUNDS,
        "scenario": SCENARIO,
        "requests_per_round": REQUESTS,
        "warmup_per_round": WARMUP,
        "methodology_notes": [
            "Preserves perf-003-end-to-end untouched.",
            "Enforces identical pre-circuit-breaker client work across native and Rust-backed paths in both TypeScript and Python:",
            "1. URL extraction and parsing (new URL() in TS; _extract_url + urlparse in Python).",
            "2. Domain/circuit-key resolution (getCircuitKey in TS; _resolve_circuit_key in Python).",
            "3. Per-domain Map/dict lookup with >1000-entry cleanup guard (Map in TS; dict + RLock in Python).",
            "4. Circuit-breaker canRequest check (native JS/Python state vs Node-API/PyO3 NativeCircuitBreaker).",
            "5. Lifecycle hook check and fallback return.",
        ],
    }
    (RESULTS_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    generate_figure(summary)
    print(f"[perf-003b] Saved results to {RESULTS_DIR} and figure to {FIGURES_DIR / 'exp-004b-fair-fast-fail.png'}")


if __name__ == "__main__":
    main()

