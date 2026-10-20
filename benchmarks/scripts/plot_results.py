import json
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

ROOT_DIR = Path(__file__).resolve().parents[2]
EXP_DIR = ROOT_DIR / "benchmarks" / "results" / "exp-001"
FIG_DIR = ROOT_DIR / "research" / "figures"

FIG_DIR.mkdir(parents=True, exist_ok=True)

# 1. Load data
raw_csv = EXP_DIR / "raw.csv"
summary_json = EXP_DIR / "summary.json"

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

# Colors (curated, modern paper palette)
colors = {
    "Rust": "#d9531e",             # Rust orange
    "TypeScript (Node)": "#3178c6", # TS blue
    "Python 3.14": "#3776ab"       # Python slate blue
}

sns.set_theme(style="whitegrid", font_scale=1.1)
plt.rcParams["font.sans-serif"] = ["Segoe UI", "DejaVu Sans", "Arial"]

# -------------------------------------------------------------
# Figure 1: Latency (ns / op)
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

plt.title("Execution Latency per Operation (Lower is Better)", fontsize=14, fontweight="bold", pad=15)
plt.ylabel("Latency (Nanoseconds / op)", fontsize=12, fontweight="semibold")
plt.xlabel("", fontsize=12)
plt.yscale("log")
plt.grid(axis="y", linestyle="--", alpha=0.6, which="both")

# Annotate bars with values
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
latency_path = FIG_DIR / "exp-001-latency.png"
plt.savefig(latency_path, dpi=300)
plt.close()
print(f"Saved: {latency_path}")

# -------------------------------------------------------------
# Figure 2: Throughput (Million ops / sec)
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

plt.title("Execution Throughput (Higher is Better)", fontsize=14, fontweight="bold", pad=15)
plt.ylabel("Throughput (Million Ops / sec)", fontsize=12, fontweight="semibold")
plt.xlabel("", fontsize=12)
plt.grid(axis="y", linestyle="--", alpha=0.6)

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
throughput_path = FIG_DIR / "exp-001-throughput.png"
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
ax1.grid(axis="y", linestyle="--", alpha=0.6, which="both")

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
ax2.grid(axis="y", linestyle="--", alpha=0.6)

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

plt.suptitle("SmoothAPI Experiment exp-001: Baseline Computation Performance", fontsize=15, fontweight="bold", y=1.02)
plt.tight_layout()
summary_path = FIG_DIR / "exp-001-summary.png"
plt.savefig(summary_path, dpi=300, bbox_inches="tight")
plt.close()
print(f"Saved: {summary_path}")
