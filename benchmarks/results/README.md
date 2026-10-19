# Benchmark Results Index

This directory holds machine-readable measurements and summaries for each recorded experiment.

## Immutability Policy
- Never overwrite an existing experiment directory.
- Repeated runs receive a new ID (e.g. `exp-001`, `exp-002`, `exp-001-pilot`).

## Directory Schema per Experiment

```text
exp-<ID>/
├── metadata.json   # Machine details, git commit, toolchain versions, configuration
├── raw.csv         # Per-round measurements across all iterations and languages
└── summary.json    # Derived statistics (mean, median, min, max, stdev, speedup ratios)
```
