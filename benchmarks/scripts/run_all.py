import argparse
import csv
import json
import math
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
CONFIG_FILE = ROOT_DIR / "benchmarks" / "config" / "benchmark.json"
RESULTS_DIR = ROOT_DIR / "benchmarks" / "results"

def get_git_commit():
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

def get_toolchain_versions():
    versions = {}
    try:
        r = subprocess.run(["rustc", "--version"], capture_output=True, text=True)
        versions["rustc"] = r.stdout.strip()
    except Exception:
        versions["rustc"] = "unknown"
    try:
        r = subprocess.run(["node", "--version"], capture_output=True, text=True)
        versions["node"] = r.stdout.strip()
    except Exception:
        versions["node"] = "unknown"
    versions["python"] = sys.version.split()[0]
    return versions

def calculate_stats(numbers):
    if not numbers:
        return {}
    s = sorted(numbers)
    n = len(s)
    mean = sum(s) / n
    median = s[n // 2] if n % 2 != 0 else (s[n // 2 - 1] + s[n // 2]) / 2.0
    variance = sum((x - mean) ** 2 for x in s) / n
    stdev = math.sqrt(variance)
    spread = s[-1] - s[0]
    spread_pct = (spread / median * 100.0) if median > 0 else 0.0
    return {
        "min": s[0],
        "max": s[-1],
        "median": median,
        "mean": mean,
        "stdev": stdev,
        "spread": spread,
        "spread_pct": round(spread_pct, 2),
    }

def run_rust(workload, iterations, warmup, round_num):
    cmd = [
        "cargo",
        "run",
        "--release",
        "--manifest-path",
        str(ROOT_DIR / "benchmarks" / "rust" / "Cargo.toml"),
        "--",
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
            return json.loads(line)
    raise RuntimeError(f"Rust benchmark output did not contain JSON: {res.stdout}")

def run_typescript(workload, iterations, warmup, round_num):
    cmd = [
        "node",
        str(ROOT_DIR / "benchmarks" / "typescript" / "bench.mjs"),
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
            return json.loads(line)
    raise RuntimeError(f"TypeScript benchmark output did not contain JSON: {res.stdout}")

def run_python(workload, iterations, warmup, round_num):
    cmd = [
        sys.executable,
        str(ROOT_DIR / "benchmarks" / "python" / "bench.py"),
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
            return json.loads(line)
    raise RuntimeError(f"Python benchmark output did not contain JSON: {res.stdout}")

RUNNERS = {
    "rust": run_rust,
    "typescript": run_typescript,
    "python": run_python,
}

def main():
    parser = argparse.ArgumentParser(description="SmoothAPI Benchmark Suite Orchestrator")
    parser.add_argument("--pilot", action="store_true", help="Run a quick pilot test")
    parser.add_argument("--experiment-id", default=None, help="Custom experiment ID (e.g. exp-001)")
    args = parser.parse_args()

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    exp_id = args.experiment_id or (config["experiment_id"] + ("-pilot" if args.pilot else ""))
    exp_dir = RESULTS_DIR / exp_id

    # Strictly disallow overwriting earlier experiments
    if exp_dir.exists():
        print(f"ERROR: Experiment directory '{exp_dir}' already exists! Never overwrite experiment results. Use a new ID.", file=sys.stderr)
        sys.exit(1)

    params = config["parameters"]["pilot"] if args.pilot else config["parameters"]["full"]
    rounds = params["rounds"]
    warmup = params["warmup_iterations"]
    calibrated_map = params.get("calibrated", {})

    workloads = ["backoff_deterministic", "retry_policy_evaluation"]
    languages = ["rust", "typescript", "python"]

    raw_records = []

    print("=" * 75)
    print(f" SmoothAPI Microbenchmark Orchestrator - Experiment: {exp_id}")
    print(f" Mode: {'PILOT' if args.pilot else 'FULL'} | Rounds: {rounds} | Warm-up: {warmup:,}")
    print("=" * 75)

    for workload in workloads:
        print(f"\n>> Workload: {workload}")
        for r in range(1, rounds + 1):
            # Counterbalance language execution order per round to mitigate systematic bias
            order = languages[(r - 1) % len(languages):] + languages[:(r - 1) % len(languages)]
            print(f"  Round {r}/{rounds} (Execution Order: {' -> '.join(order)})")

            for lang in order:
                runner = RUNNERS[lang]
                # Determine calibrated iterations if available
                if calibrated_map and workload in calibrated_map and lang in calibrated_map[workload]:
                    iters = calibrated_map[workload][lang]
                else:
                    iters = params.get("iterations", 1_000_000)

                try:
                    result = runner(workload, iters, warmup, r)
                    raw_records.append(result)
                    print(f"    [{lang:<10}] {result['ns_per_op']:>8.2f} ns/op | {result['ops_per_sec']:>14,.0f} ops/sec ({result['elapsed_ms']:>7.2f} ms | {result['iterations']:>11,} iters)")
                except Exception as err:
                    print(f"    [{lang:<10}] FAILED: {err}", file=sys.stderr)
                    sys.exit(1)

    # Process and summarize statistics
    summary = {"experiment_id": exp_id, "workloads": {}}

    for workload in workloads:
        summary["workloads"][workload] = {}
        for lang in languages:
            records = [rec for rec in raw_records if rec["workload"] == workload and rec["language"] == lang]
            ns_ops = [rec["ns_per_op"] for rec in records]
            ops_secs = [rec["ops_per_sec"] for rec in records]
            elapsed_mss = [rec["elapsed_ms"] for rec in records]
            iter_counts = [rec["iterations"] for rec in records]

            summary["workloads"][workload][lang] = {
                "sample_iterations": iter_counts[0] if iter_counts else 0,
                "ns_per_op": calculate_stats(ns_ops),
                "ops_per_sec": calculate_stats(ops_secs),
                "elapsed_ms": calculate_stats(elapsed_mss),
            }

        rust_median = summary["workloads"][workload]["rust"]["ns_per_op"]["median"]
        ts_median = summary["workloads"][workload]["typescript"]["ns_per_op"]["median"]
        py_median = summary["workloads"][workload]["python"]["ns_per_op"]["median"]

        summary["workloads"][workload]["relative_overhead_vs_rust"] = {
            "typescript_ratio": round(ts_median / rust_median, 2) if rust_median > 0 else 0,
            "python_ratio": round(py_median / rust_median, 2) if rust_median > 0 else 0,
        }

    metadata = {
        "experiment_id": exp_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": get_git_commit(),
        "mode": "pilot" if args.pilot else "full",
        "system": {
            "os": platform.platform(),
            "processor": platform.processor(),
            "machine": platform.machine(),
        },
        "toolchains": get_toolchain_versions(),
        "parameters": {
            "rounds": rounds,
            "warmup_iterations": warmup,
            "workloads": workloads,
            "calibrated_iterations": calibrated_map,
        },
        "methodology_notes": [
            "Calibrated iterations target 0.5-1.0 second duration per measured sample across all runtimes.",
            "Correctness checks run strictly outside timed loops.",
            "Test vectors are pre-allocated outside timed loop; loop executes in 5-iteration batches without modulo math.",
            "DCE prevention via black_box in Rust and sink accumulation across all languages.",
            "Language execution order is counterbalanced across rounds."
        ]
    }

    # Save to disk
    exp_dir.mkdir(parents=True, exist_ok=False)

    with open(exp_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    with open(exp_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    with open(exp_dir / "raw.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["workload", "language", "round", "iterations", "elapsed_ms", "ops_per_sec", "ns_per_op"],
        )
        writer.writeheader()
        writer.writerows(raw_records)

    print("\n" + "=" * 75)
    print(f" Experiment completed successfully! Results written to: {exp_dir}")
    print("=" * 75)

    # Print summary table
    for workload in workloads:
        print(f"\n--- Summary: {workload} ---")
        w_data = summary["workloads"][workload]
        for lang in languages:
            med_ns = w_data[lang]["ns_per_op"]["median"]
            med_ops = w_data[lang]["ops_per_sec"]["median"]
            stdev_ns = w_data[lang]["ns_per_op"]["stdev"]
            spread_pct = w_data[lang]["ns_per_op"]["spread_pct"]
            med_ms = w_data[lang]["elapsed_ms"]["median"]
            print(f"  {lang:<10}: {med_ns:>7.2f} ns/op (+/-{stdev_ns:.2f}, {spread_pct}% spread) | {med_ops:>13,.0f} ops/sec (Sample: {med_ms:>6.1f} ms)")
        ratios = w_data["relative_overhead_vs_rust"]
        print(f"  Relative execution cost vs Rust: TS is {ratios['typescript_ratio']}x | Python is {ratios['python_ratio']}x")

if __name__ == "__main__":
    main()
