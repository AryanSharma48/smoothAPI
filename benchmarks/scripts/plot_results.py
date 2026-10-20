import argparse
import json
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

ROOT_DIR = Path(__file__).resolve().parents[2]
FIG_DIR = ROOT_DIR / "research" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

def main():
    parser = argparse.ArgumentParser(description="SmoothAPI Benchmark Plotting")
    parser.add_argument("--experiment-id", default="exp-001", help="Experiment ID to plot (default: exp-001)")
    args = parser.parse_args()

    exp_id = args.experiment_id
    exp_dir = ROOT_DIR / "benchmarks" / "results" / exp_id

    if not exp_dir.exists():
        raise FileNotFoundError(f"Experiment directory not found: {exp_dir}")

    raw_csv = exp_dir / "raw.csv"
    summary_json = exp_dir / "summary.json"

    df = pd.read_csv(raw_csv)
    with open(summary_json, "r", encoding="utf-8") as f:
        summary = json.load(f)

    # Pretty names
    df["Language"] = df["language"].map({
        "rust": "Rust",
        "typescript": "TypeScript (Node)",
        "python": "Python 3.14"
    })
    df["Workload"] = df["workload"].map({
        "backoff_deterministic": "Backoff Calculation",
        "retry_policy_evaluation": "Retry Policy Evaluation"
    })
    df["m_ops_sec"] = df["ops_per_sec"] / 1_000_000.0

    # Colors (curated, modern publication palette)
    colors = {
        "Rust": "#d9531e",             # Rust orange
        "TypeScript (Node)": "#3178c6", # TS blue
        "Python 3.14": "#3776ab"       # Python slate blue
    }

    sns.set_theme(style="whitegrid", font_scale=1.1)
    plt.rcParams["font.sans-serif"] = ["Segoe UI", "DejaVu Sans", "Arial"]

    # -------------------------------------------------------------
    # Figure 1: Latency (ns / op, Log Scale)
    # -------------------------------------------------------------
    plt.figure(figsize=(9, 5.5), dpi=300)
    ax = sns.barplot(
        data=df,
        x="Workload",
        y="ns_per_op",
        hue="Language",
        palette=colors,
        errorbar=None,
    )

    plt.title(f"Execution Latency per Operation ({exp_id}) - Lower is Better", fontsize=14, fontweight="bold", pad=15)
    plt.ylabel("Latency (Nanoseconds / op, Log Scale)", fontsize=12, fontweight="semibold")
    plt.xlabel("", fontsize=12)
    plt.yscale("log")
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, which="major", linestyle="-", color="#e5e7eb", linewidth=0.8)
    ax.yaxis.grid(False, which="minor")
    ax.xaxis.grid(False)

    for p in ax.patches:
        h = p.get_height()
        if h > 0:
            ax.annotate(
                f"{h:.1f} ns",
                (p.get_x() + p.get_width() / 2.0, h),
                ha="center",
                va="bottom",
                xytext=(0, 4),
                textcoords="offset points",
                fontsize=9.5,
                fontweight="bold",
            )

    plt.legend(title="Runtime", frameon=True, facecolor="white", edgecolor="#ddd")
    plt.tight_layout()
    latency_path = FIG_DIR / f"{exp_id}-latency.png"
    plt.savefig(latency_path, dpi=300)
    plt.close()
    print(f"Saved: {latency_path}")

    # -------------------------------------------------------------
    # Figure 2: Throughput (Million ops / sec, Linear Scale)
    # -------------------------------------------------------------
    plt.figure(figsize=(9, 5.5), dpi=300)
    ax = sns.barplot(
        data=df,
        x="Workload",
        y="m_ops_sec",
        hue="Language",
        palette=colors,
        errorbar=None,
    )

    plt.title(f"Execution Throughput ({exp_id}) - Higher is Better", fontsize=14, fontweight="bold", pad=15)
    plt.ylabel("Throughput (Million Ops / sec)", fontsize=12, fontweight="semibold")
    plt.xlabel("", fontsize=12)
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, which="major", linestyle="-", color="#e5e7eb", linewidth=0.8)
    ax.xaxis.grid(False)

    for p in ax.patches:
        h = p.get_height()
        if h > 0:
            ax.annotate(
                f"{h:.1f}M",
                (p.get_x() + p.get_width() / 2.0, h),
                ha="center",
                va="bottom",
                xytext=(0, 4),
                textcoords="offset points",
                fontsize=9.5,
                fontweight="bold",
            )

    plt.legend(title="Runtime", frameon=True, facecolor="white", edgecolor="#ddd")
    plt.tight_layout()
    throughput_path = FIG_DIR / f"{exp_id}-throughput.png"
    plt.savefig(throughput_path, dpi=300)
    plt.close()
    print(f"Saved: {throughput_path}")

    # -------------------------------------------------------------
    # Figure 3: Combined Two-Panel Publication Figure
    # -------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 5.5), dpi=300)

    # Panel A: Latency
    sns.barplot(
        data=df,
        x="Workload",
        y="ns_per_op",
        hue="Language",
        palette=colors,
        errorbar=None,
        ax=ax1,
    )
    ax1.set_title("A. Latency per Operation (Log Scale, Lower is Better)", fontsize=12, fontweight="bold")
    ax1.set_ylabel("Latency (ns / op, log scale)", fontsize=11)
    ax1.set_xlabel("")
    ax1.set_yscale("log")
    ax1.set_axisbelow(True)
    ax1.yaxis.grid(True, which="major", linestyle="-", color="#e5e7eb", linewidth=0.8)
    ax1.yaxis.grid(False, which="minor")
    ax1.xaxis.grid(False)

    for p in ax1.patches:
        h = p.get_height()
        if h > 0:
            ax1.annotate(
                f"{h:.1f} ns",
                (p.get_x() + p.get_width() / 2.0, h),
                ha="center",
                va="bottom",
                xytext=(0, 3),
                textcoords="offset points",
                fontsize=9,
                fontweight="bold",
            )

    # Panel B: Throughput
    sns.barplot(
        data=df,
        x="Workload",
        y="m_ops_sec",
        hue="Language",
        palette=colors,
        errorbar=None,
        ax=ax2,
    )
    ax2.set_title("B. Throughput (Linear Scale, Higher is Better)", fontsize=12, fontweight="bold")
    ax2.set_ylabel("Throughput (Million ops / sec)", fontsize=11)
    ax2.set_xlabel("")
    ax2.set_axisbelow(True)
    ax2.yaxis.grid(True, which="major", linestyle="-", color="#e5e7eb", linewidth=0.8)
    ax2.xaxis.grid(False)

    for p in ax2.patches:
        h = p.get_height()
        if h > 0:
            ax2.annotate(
                f"{h:.1f}M",
                (p.get_x() + p.get_width() / 2.0, h),
                ha="center",
                va="bottom",
                xytext=(0, 3),
                textcoords="offset points",
                fontsize=9,
                fontweight="bold",
            )

    ax1.get_legend().remove()
    ax2.legend(title="Runtime", frameon=True, facecolor="white", edgecolor="#ddd")

    plt.suptitle(f"SmoothAPI Experiment {exp_id}: Baseline Computation Performance (Calibrated Durations)", fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout()
    summary_path = FIG_DIR / f"{exp_id}-summary.png"
    plt.savefig(summary_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved: {summary_path}")

if __name__ == "__main__":
    main()
