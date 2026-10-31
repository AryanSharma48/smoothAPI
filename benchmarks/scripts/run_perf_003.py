"""Orchestrator for Experiment 3 (perf-003-end-to-end): End-to-End API Client Performance.

Compares 4 full API client implementations across 3 HTTP scenarios against a local keep-alive server:
  - ts_native  : Native TypeScript (createSmoothFetch)
  - ts_napi    : Rust-backed TypeScript (bindings/node via Node-API)
  - py_native  : Native Python (@smooth_api)
  - py_pyo3    : Rust-backed Python (smoothapi_rs via PyO3, GIL held)

Scenarios:
  1. normal_200            : Baseline HTTP 200 OK request overhead
  2. intermittent_503_429  : 1st attempt HTTP 429 (Retry-After: 0), 2nd attempt HTTP 200 OK
  3. repeated_failures_cb  : Persistent HTTP 503 trips circuit breaker after 3 requests;
                             remaining requests fast-fail in-process via OPEN circuit fallback

Outputs:
  - benchmarks/results/perf-003-end-to-end/raw.csv
  - benchmarks/results/perf-003-end-to-end/metadata.json
  - benchmarks/results/perf-003-end-to-end/summary.json
  - benchmarks/research/figures/exp-004-throughput.png
  - benchmarks/research/figures/exp-004-latency.png
  - benchmarks/research/figures/exp-004-cpu-memory.png
  - benchmarks/research/figures/exp-004-speedup.png
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
RESULTS_DIR = ROOT_DIR / "benchmarks" / "results" / "perf-003-end-to-end"
FIGURES_DIR = ROOT_DIR / "benchmarks" / "research" / "figures"

PORT = 3099
BASE_URL = f"http://127.0.0.1:{PORT}"
ROUNDS = 5

SCENARIOS = [
    {
        "id": "normal_200",
        "title": "Normal HTTP 200 (Baseline)",
        "requests": 400,
        "warmup": 40,
    },
    {
        "id": "intermittent_503_429",
        "title": "Intermittent 429/503 (1 Retry/Req)",
        "requests": 250,
        "warmup": 30,
    },
    {
        "id": "repeated_failures_cb",
        "title": "Repeated Failures (Circuit Breaker Fast-Fail)",
        "requests": 10000,
        "warmup": 20,
    },
]

IMPLEMENTATIONS = [
    ("ts_native", "Native TypeScript"),
    ("ts_napi", "TypeScript + Node-API (Rust)"),
    ("py_native", "Native Python"),
    ("py_pyo3", "Python + PyO3 (Rust, GIL held)"),
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


def run_single(impl: str, scenario: str, requests: int, warmup: int, round_num: int) -> dict:
    if impl.startswith("ts_"):
        script = ROOT_DIR / "benchmarks" / "typescript" / "bench_e2e.mjs"
        cmd = [
            "node",
            str(script),
            "--impl",
            impl,
            "--scenario",
            scenario,
            "--url",
            BASE_URL,
            "--requests",
            str(requests),
            "--warmup",
            str(warmup),
            "--round",
            str(round_num),
        ]
    else:
        script = ROOT_DIR / "benchmarks" / "python" / "bench_e2e.py"
        cmd = [
            sys.executable,
            str(script),
            "--impl",
            impl,
            "--scenario",
            scenario,
            "--url",
            BASE_URL,
            "--requests",
            str(requests),
            "--warmup",
            str(warmup),
            "--round",
            str(round_num),
        ]

    res = subprocess.run(cmd, cwd=str(ROOT_DIR), capture_output=True, text=True, check=True)
    for line in reversed(res.stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            return json.loads(line)
    raise RuntimeError(f"Failed to parse JSON output from {cmd}: {res.stdout}")


def aggregate_summary(raw_rows: list[dict]) -> dict:
    summary: dict = {"scenarios": {}, "relative_speedups": {}}
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

    for sc in SCENARIOS:
        sc_id = sc["id"]
        summary["scenarios"][sc_id] = {}
        for impl_id, impl_label in IMPLEMENTATIONS:
            rows = [r for r in raw_rows if r["scenario"] == sc_id and r["impl"] == impl_id]
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
            summary["scenarios"][sc_id][impl_id] = entry

        ts_nat_rps = summary["scenarios"][sc_id]["ts_native"]["req_per_sec"]["mean"]
        ts_napi_rps = summary["scenarios"][sc_id]["ts_napi"]["req_per_sec"]["mean"]
        py_nat_rps = summary["scenarios"][sc_id]["py_native"]["req_per_sec"]["mean"]
        py_pyo3_rps = summary["scenarios"][sc_id]["py_pyo3"]["req_per_sec"]["mean"]

        ts_nat_cpu = summary["scenarios"][sc_id]["ts_native"]["cpu_ms_per_1k_reqs"]["mean"]
        ts_napi_cpu = summary["scenarios"][sc_id]["ts_napi"]["cpu_ms_per_1k_reqs"]["mean"]
        py_nat_cpu = summary["scenarios"][sc_id]["py_native"]["cpu_ms_per_1k_reqs"]["mean"]
        py_pyo3_cpu = summary["scenarios"][sc_id]["py_pyo3"]["cpu_ms_per_1k_reqs"]["mean"]

        summary["relative_speedups"][sc_id] = {
            "ts_napi_vs_ts_native_rps_ratio": round(ts_napi_rps / ts_nat_rps, 4),
            "py_pyo3_vs_py_native_rps_ratio": round(py_pyo3_rps / py_nat_rps, 4),
            "ts_native_vs_py_native_rps_ratio": round(ts_nat_rps / py_nat_rps, 4),
            "ts_napi_vs_ts_native_cpu_reduction": round(ts_nat_cpu / ts_napi_cpu, 4) if ts_napi_cpu > 0 else 1.0,
            "py_pyo3_vs_py_native_cpu_reduction": round(py_nat_cpu / py_pyo3_cpu, 4) if py_pyo3_cpu > 0 else 1.0,
        }

    return summary


def generate_figures(summary: dict) -> None:
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

    colors = {
        "ts_native": "#0284c7",
        "ts_napi": "#38bdf8",
        "py_native": "#d97706",
        "py_pyo3": "#10b981",
    }
    labels = {k: v for k, v in IMPLEMENTATIONS}

    # ------------------------------------------------------------------
    # 1. Requests per Second (e2e_throughput.png)
    # ------------------------------------------------------------------
    fig, axes = plt.subplots(1, 3, figsize=(15, 5.2), dpi=180)
    fig.suptitle(
        "Experiment 3 (perf-003): End-to-End API Client Throughput (Requests / sec)",
        fontsize=13,
        fontweight="bold",
        y=0.98,
    )

    for idx, sc in enumerate(SCENARIOS):
        ax = axes[idx]
        sc_id = sc["id"]
        impl_keys = [k for k, _ in IMPLEMENTATIONS]
        means = [summary["scenarios"][sc_id][k]["req_per_sec"]["mean"] for k in impl_keys]
        cis = [summary["scenarios"][sc_id][k]["req_per_sec"]["ci95"] for k in impl_keys]
        x = np.arange(len(impl_keys))

        bars = ax.bar(
            x,
            means,
            yerr=cis,
            capsize=4,
            color=[colors[k] for k in impl_keys],
            edgecolor="#0f172a",
            linewidth=0.7,
            width=0.62,
        )
        ax.set_title(sc["title"], fontsize=10.5, fontweight="bold", pad=10)
        ax.set_xticks(x)
        ax.set_xticklabels(["TS\nNative", "TS +\nNode-API", "Python\nNative", "Python +\nPyO3"], fontsize=9)
        ax.set_ylabel("Requests / sec (Higher is better)" if idx == 0 else "")
        ax.grid(axis="y", linestyle="--", alpha=0.35)
        ax.set_ylim(0, max(means) * 1.22)

        for bar, m in zip(bars, means):
            lbl = f"{m:,.0f}" if m >= 100 else f"{m:,.1f}"
            ax.text(
                bar.get_x() + bar.get_width() / 2.0,
                bar.get_height() + max(means) * 0.03,
                lbl,
                ha="center",
                va="bottom",
                fontsize=8.5,
                fontweight="bold",
            )

    fig.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(FIGURES_DIR / "exp-004-throughput.png")
    plt.close(fig)

    # ------------------------------------------------------------------
    # 2. P50, P95, and P99 Latency (e2e_latency_percentiles.png)
    # ------------------------------------------------------------------
    fig, axes = plt.subplots(1, 3, figsize=(15.5, 5.4), dpi=180)
    fig.suptitle(
        "Experiment 3 (perf-003): End-to-End Request Latency Percentiles (P50, P95, P99)",
        fontsize=13,
        fontweight="bold",
        y=0.98,
    )

    pct_keys = [("p50_ms", "P50"), ("p95_ms", "P95"), ("p99_ms", "P99")]
    width = 0.19
    x = np.arange(len(pct_keys))

    for idx, sc in enumerate(SCENARIOS):
        ax = axes[idx]
        sc_id = sc["id"]
        max_val = 0.0
        for i_idx, (impl_key, impl_lbl) in enumerate(IMPLEMENTATIONS):
            vals = [summary["scenarios"][sc_id][impl_key][pk]["mean"] for pk, _ in pct_keys]
            max_val = max(max_val, max(vals))
            offset = (i_idx - 1.5) * width
            bars = ax.bar(
                x + offset,
                vals,
                width=width,
                label=impl_lbl if idx == 0 else None,
                color=colors[impl_key],
                edgecolor="#0f172a",
                linewidth=0.6,
            )
            for bar, v in zip(bars, vals):
                txt = f"{v:.3f}" if v < 0.1 else f"{v:.2f}"
                ax.text(
                    bar.get_x() + bar.get_width() / 2.0,
                    bar.get_height() + max_val * 0.02,
                    txt,
                    ha="center",
                    va="bottom",
                    fontsize=7,
                    rotation=45,
                )

        ax.set_title(sc["title"], fontsize=10.5, fontweight="bold", pad=10)
        ax.set_xticks(x)
        ax.set_xticklabels([lbl for _, lbl in pct_keys], fontsize=9.5)
        ax.set_ylabel("Latency in ms (Lower is better)" if idx == 0 else "")
        ax.grid(axis="y", linestyle="--", alpha=0.35)
        ax.set_ylim(0, max_val * 1.30)

    fig.legend(loc="upper center", bbox_to_anchor=(0.5, 0.93), ncol=4, frameon=True, fontsize=9)
    fig.tight_layout(rect=[0, 0, 1, 0.87])
    fig.savefig(FIGURES_DIR / "exp-004-latency.png")
    plt.close(fig)

    # ------------------------------------------------------------------
    # 3. CPU and Memory Consumption (e2e_cpu_memory.png)
    # ------------------------------------------------------------------
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.2), dpi=180)
    fig.suptitle(
        "Experiment 3 (perf-003): End-to-End CPU Time per 1,000 Requests & Process Memory (RSS)",
        fontsize=13,
        fontweight="bold",
        y=0.98,
    )

    sc_labels = ["Normal 200", "Intermittent 429/503", "Fast-Fail CB (OPEN)"]
    x = np.arange(len(SCENARIOS))
    width = 0.19

    # Panel A: CPU ms per 1,000 requests (log scale because Fast-Fail CB is ~1000x smaller than HTTP I/O)
    ax_cpu = axes[0]
    for i_idx, (impl_key, impl_lbl) in enumerate(IMPLEMENTATIONS):
        vals = [
            max(0.001, summary["scenarios"][sc["id"]][impl_key]["cpu_ms_per_1k_reqs"]["mean"])
            for sc in SCENARIOS
        ]
        offset = (i_idx - 1.5) * width
        bars = ax_cpu.bar(
            x + offset,
            vals,
            width=width,
            label=impl_lbl,
            color=colors[impl_key],
            edgecolor="#0f172a",
            linewidth=0.6,
        )
        for bar, v in zip(bars, vals):
            lbl = f"{v:.2f}" if v < 10 else f"{v:.0f}"
            ax_cpu.text(
                bar.get_x() + bar.get_width() / 2.0,
                bar.get_height() * 1.12,
                lbl,
                ha="center",
                va="bottom",
                fontsize=7.5,
            )

    ax_cpu.set_yscale("log")
    ax_cpu.set_title("CPU Time (ms) per 1,000 Requests (Log Scale)", fontsize=10.5, fontweight="bold")
    ax_cpu.set_xticks(x)
    ax_cpu.set_xticklabels(sc_labels, fontsize=9.5)
    ax_cpu.set_ylabel("CPU ms / 1,000 requests (Lower is better)")
    ax_cpu.grid(axis="y", linestyle="--", alpha=0.35)
    ax_cpu.set_ylim(0.005, 5000)

    # Panel B: Peak Process Memory RSS (MB)
    ax_mem = axes[1]
    max_rss = 0.0
    for i_idx, (impl_key, impl_lbl) in enumerate(IMPLEMENTATIONS):
        vals = [summary["scenarios"][sc["id"]][impl_key]["rss_mb"]["mean"] for sc in SCENARIOS]
        max_rss = max(max_rss, max(vals))
        offset = (i_idx - 1.5) * width
        bars = ax_mem.bar(
            x + offset,
            vals,
            width=width,
            color=colors[impl_key],
            edgecolor="#0f172a",
            linewidth=0.6,
        )
        for bar, v in zip(bars, vals):
            ax_mem.text(
                bar.get_x() + bar.get_width() / 2.0,
                bar.get_height() + max_rss * 0.02,
                f"{v:.1f}",
                ha="center",
                va="bottom",
                fontsize=7.5,
            )

    ax_mem.set_title("Process Working Set / RSS Memory (MB)", fontsize=10.5, fontweight="bold")
    ax_mem.set_xticks(x)
    ax_mem.set_xticklabels(sc_labels, fontsize=9.5)
    ax_mem.set_ylabel("Memory RSS in MB (Lower is better)")
    ax_mem.grid(axis="y", linestyle="--", alpha=0.35)
    ax_mem.set_ylim(0, max_rss * 1.25)

    fig.legend(loc="upper center", bbox_to_anchor=(0.5, 0.93), ncol=4, frameon=True, fontsize=9)
    fig.tight_layout(rect=[0, 0, 1, 0.87])
    fig.savefig(FIGURES_DIR / "exp-004-cpu-memory.png")
    plt.close(fig)

    # ------------------------------------------------------------------
    # 4. Relative Performance: Microbenchmark vs End-to-End (e2e_relative_speedup.png)
    # ------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(11, 5.2), dpi=180)
    categories = [
        "Microbench:\nBackoff (perf-001)",
        "Microbench:\nRetry Eval (perf-001)",
        "Microbench:\nCircuit Breaker (perf-001)",
        "E2E: Normal\nHTTP 200 (perf-003)",
        "E2E: Intermittent\n429/503 (perf-003)",
        "E2E: Fast-Fail\nOPEN Circuit (perf-003)",
    ]

    ts_ratios = [
        0.40,
        0.03,
        0.15,
        summary["relative_speedups"]["normal_200"]["ts_napi_vs_ts_native_rps_ratio"],
        summary["relative_speedups"]["intermittent_503_429"]["ts_napi_vs_ts_native_rps_ratio"],
        summary["relative_speedups"]["repeated_failures_cb"]["ts_napi_vs_ts_native_rps_ratio"],
    ]
    py_ratios = [
        5.82,
        1.01,
        12.78,
        summary["relative_speedups"]["normal_200"]["py_pyo3_vs_py_native_rps_ratio"],
        summary["relative_speedups"]["intermittent_503_429"]["py_pyo3_vs_py_native_rps_ratio"],
        summary["relative_speedups"]["repeated_failures_cb"]["py_pyo3_vs_py_native_rps_ratio"],
    ]

    x = np.arange(len(categories))
    w = 0.34
    bars_ts = ax.bar(
        x - w / 2,
        ts_ratios,
        width=w,
        label="TypeScript: Node-API (Rust) vs Native TS",
        color="#38bdf8",
        edgecolor="#0f172a",
        linewidth=0.7,
    )
    bars_py = ax.bar(
        x + w / 2,
        py_ratios,
        width=w,
        label="Python: PyO3 (Rust) vs Native Python",
        color="#10b981",
        edgecolor="#0f172a",
        linewidth=0.7,
    )

    ax.axhline(1.0, color="#ef4444", linestyle="--", linewidth=1.3, label="Parity (1.00x)")
    ax.set_title(
        "Relative Speedup (Rust-Backed vs Native Host) Across Microbenchmarks & End-to-End Client",
        fontsize=12,
        fontweight="bold",
        pad=12,
    )
    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=9)
    ax.set_ylabel("Speedup Ratio (Rust-Backed / Native Host, >1.0x = Rust Faster)")
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    max_r = max(max(ts_ratios), max(py_ratios))
    ax.set_ylim(0, max_r * 1.20)

    for bar, v in zip(bars_ts, ts_ratios):
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            bar.get_height() + max_r * 0.02,
            f"{v:.2f}x",
            ha="center",
            va="bottom",
            fontsize=8.5,
            fontweight="bold",
        )
    for bar, v in zip(bars_py, py_ratios):
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            bar.get_height() + max_r * 0.02,
            f"{v:.2f}x",
            ha="center",
            va="bottom",
            fontsize=8.5,
            fontweight="bold",
        )

    ax.legend(loc="upper right", frameon=True, fontsize=9.5)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "exp-004-speedup.png")
    plt.close(fig)


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    server_proc = start_server()
    print(f"[perf-003] Controlled HTTP server listening on {BASE_URL}")

    raw_rows: list[dict] = []
    try:
        for r in range(1, ROUNDS + 1):
            # Counterbalance implementation execution order across rounds
            shift = (r - 1) % len(IMPLEMENTATIONS)
            ordered_impls = IMPLEMENTATIONS[shift:] + IMPLEMENTATIONS[:shift]
            for sc in SCENARIOS:
                sc_id = sc["id"]
                for impl_id, _ in ordered_impls:
                    row = run_single(
                        impl=impl_id,
                        scenario=sc_id,
                        requests=sc["requests"],
                        warmup=sc["warmup"],
                        round_num=r,
                    )
                    raw_rows.append(row)
                    print(
                        f"  [Round {r}/{ROUNDS}] {sc_id:<22} | {impl_id:<10} | "
                        f"{row['req_per_sec']:>10.2f} req/s | "
                        f"P50={row['p50_ms']:.3f}ms P99={row['p99_ms']:.3f}ms | "
                        f"CPU/1k={row['cpu_ms_per_1k_reqs']:.2f}ms | RSS={row['rss_mb']:.1f}MB"
                    )
    finally:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except Exception:
            server_proc.kill()

    # Write raw.csv
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
    raw_csv_path = RESULTS_DIR / "raw.csv"
    with raw_csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(raw_rows)

    summary = aggregate_summary(raw_rows)
    summary_path = RESULTS_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    node_ver = subprocess.run(
        ["node", "--version"], capture_output=True, text=True, check=False
    ).stdout.strip()
    metadata = {
        "experiment_id": "perf-003-end-to-end",
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "os": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python_version": sys.version,
        "node_version": node_ver,
        "rounds": ROUNDS,
        "server": f"Node.js http.createServer keep-alive on {BASE_URL}",
        "scenarios": SCENARIOS,
        "implementations": [k for k, _ in IMPLEMENTATIONS],
        "architectural_policy": "PyO3 keeps GIL held per Experiment 2 (perf-002) findings",
    }
    (RESULTS_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    generate_figures(summary)
    print(f"[perf-003] Saved results to {RESULTS_DIR} and figures to {FIGURES_DIR}")


if __name__ == "__main__":
    main()

