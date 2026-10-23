"""Differential verification orchestrator for SmoothAPI.

Runs the canonical vectors in benchmarks/config/differential_vectors.json against
all five implementations and scores each normative common-domain observation against
the documented specification:

  rust_direct  Direct Rust (smooth-api-core)
  ts_native    Native TypeScript (production createSmoothFetch / CircuitBreakerState)
  ts_napi      TypeScript -> Node-API -> Rust (bindings/node)
  py_native    Native Python (production @smooth_api / CircuitBreakerState)
  py_pyo3      Python -> PyO3 -> Rust (bindings/python)

Before scoring, expected values in the vectors file are verified against an
independent specification model (exact integer arithmetic, RFC 9110 delta-seconds,
and 2xx/3xx no-retry semantics).

Normative common-domain suites are scored pass/fail. Language-specific numeric
boundary vectors (> 2^53-1 or non-dyadic float-seconds conversions) and any
exploratory/ambiguous vectors are reported separately without inflating or deflating
normative denominators.

Usage: python benchmarks/scripts/run_differential.py [--json-out PATH] [--only IMPL ...]
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VECTORS = ROOT / "benchmarks" / "config" / "differential_vectors.json"
TESTS = ROOT / "benchmarks" / "tests"
IMPLS = ["rust_direct", "ts_native", "ts_napi", "py_native", "py_pyo3"]
RETRY_ON = {429, 500, 502, 503, 504}


# ── Independent spec model ─────────────────────────────────────────────────────
def spec_backoff(base: int, max_: int, attempt: int) -> int:
    if base <= 0 or max_ <= 0:
        return 0
    if base >= max_:
        return max_
    return min(max_, base * (2**attempt))


def spec_jitter(v: dict) -> int:
    base = int(v["base_delay_ms"])
    max_ = int(v["max_delay_ms"])
    attempt = int(v["attempt"])
    capped = spec_backoff(base, max_, attempt)
    if capped == 0:
        return 0
    factor = max(0.0, min(1.0, float(v["random_factor"])))
    strategy = v["strategy"]
    if strategy == "default":
        strategy = "equal"
    if strategy == "none":
        return capped
    if strategy == "full":
        return int(math.floor(capped * factor))
    if strategy == "equal":
        half = capped // 2
        return half + int(math.floor(half * factor))
    if strategy == "decorrelated":
        prev = int(v["prev_delay_ms"]) if v["prev_delay_ms"] is not None else base
        upper = max(base, prev * 3)
        return min(max_, base + int(math.floor((upper - base) * factor)))
    raise ValueError(f"Unknown jitter strategy: {strategy}")


def spec_retry_after(value: str | None) -> int | None:
    if value is None:
        return None
    stripped = value.strip(" \t\r\n")
    if not re.fullmatch(r"[0-9]+", stripped):
        return None
    seconds = int(stripped)
    return seconds * 1000


def spec_retry(vec: dict, cfg: dict) -> dict:
    status, attempt = vec["status"], vec["attempt"]
    if 200 <= status < 400:
        return {"decision": "Success"}
    if status not in RETRY_ON:
        return {"decision": "Terminal"}
    if attempt >= vec["max_retries"]:
        return {"decision": "Exhausted"}
    delay = spec_backoff(int(cfg["base_delay_ms"]), int(cfg["max_delay_ms"]), attempt)
    if status == 429:
        override = spec_retry_after(vec["retry_after"])
        if override is not None:
            delay = override
    return {"decision": "Retry", "delay_ms": str(delay)}


def self_check(doc: dict) -> list[str]:
    problems = []
    for v in doc["backoff"]:
        derived = str(spec_backoff(int(v["base_delay_ms"]), int(v["max_delay_ms"]), v["attempt"]))
        if derived != v["expected_ms"]:
            problems.append(f"{v['id']}: vectors say {v['expected_ms']}, spec model derives {derived}")
    for v in doc.get("jitter", []):
        derived = str(spec_jitter(v))
        if derived != v["expected_ms"]:
            problems.append(f"{v['id']}: vectors say {v['expected_ms']}, spec model derives {derived}")
    for v in doc.get("backoff_numeric_boundary", []):
        derived = str(spec_backoff(int(v["base_delay_ms"]), int(v["max_delay_ms"]), v["attempt"]))
        if derived != v["exact_u64_ms"]:
            problems.append(f"{v['id']}: vectors say {v['exact_u64_ms']}, spec model derives {derived}")
    for v in doc["retry_policy"]:
        if v["spec_status"] != "normative":
            continue
        derived = spec_retry(v, doc["retry_policy_config"])
        if derived != v["expected"]:
            problems.append(f"{v['id']}: vectors say {v['expected']}, spec model derives {derived}")
    return problems


# ── Runner execution ───────────────────────────────────────────────────────────
def command_for(impl: str) -> tuple[list[str], Path]:
    if impl == "rust_direct":
        return (
            ["cargo", "run", "--quiet", "--release", "--bin", "differential", "--", str(VECTORS)],
            ROOT / "benchmarks" / "rust",
        )
    if impl in ("ts_native", "ts_napi"):
        return (["node", str(TESTS / "test_node_differential.mjs"), "--impl", impl, str(VECTORS)], ROOT)
    return ([sys.executable, str(TESTS / "test_python_differential.py"), "--impl", impl, str(VECTORS)], ROOT)


def run_impl(impl: str) -> dict:
    cmd, cwd = command_for(impl)
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"{impl} runner failed (exit {proc.returncode}):\n{proc.stderr.strip()}")
    last_line = proc.stdout.strip().splitlines()[-1]
    return json.loads(last_line)


# ── Scoring ────────────────────────────────────────────────────────────────────
def fmt_retry(obs: dict) -> str:
    if "error" in obs:
        return f"ERROR({obs['error']})"
    if obs.get("decision") == "Retry":
        return f"Retry({obs.get('delay_ms')}ms)"
    return str(obs.get("decision"))


def score(doc: dict, reports: dict) -> tuple[list[dict], list[dict], list[dict]]:
    mismatches: list[dict] = []
    numeric_boundaries: list[dict] = []
    ambiguous: list[dict] = []

    for v in doc["backoff"]:
        for impl, rep in reports.items():
            obs = rep["results"]["backoff"].get(v["id"], {"error": "missing"})
            actual = obs.get("value", f"ERROR({obs.get('error')})")
            if actual != v["expected_ms"]:
                mismatches.append({
                    "suite": "backoff", "id": v["id"], "impl": impl, "tags": v["tags"],
                    "expected": v["expected_ms"], "actual": actual,
                    "input_lossy": obs.get("input_lossy", False),
                })

    for v in doc.get("jitter", []):
        for impl, rep in reports.items():
            obs = rep["results"].get("jitter", {}).get(v["id"], {"error": "missing"})
            actual = obs.get("value", f"ERROR({obs.get('error')})")
            if actual != v["expected_ms"]:
                mismatches.append({
                    "suite": "jitter", "id": v["id"], "impl": impl, "tags": v["tags"],
                    "strategy": v["strategy"], "expected": v["expected_ms"], "actual": actual,
                })

    for v in doc.get("backoff_numeric_boundary", []):
        row = {}
        for impl, rep in reports.items():
            obs = rep["results"].get("backoff_numeric_boundary", {}).get(v["id"], {"error": "missing"})
            actual = obs.get("value", f"ERROR({obs.get('error')})")
            row[impl] = {
                "observed": actual,
                "matches_exact_u64": actual == v["exact_u64_ms"],
                "input_lossy": obs.get("input_lossy", False),
            }
        numeric_boundaries.append({
            "id": v["id"],
            "exact_u64_ms": v["exact_u64_ms"],
            "tags": v["tags"],
            "by_impl": row,
        })

    for v in doc["retry_policy"]:
        expected = v["expected"]
        row = {}
        for impl, rep in reports.items():
            obs = rep["results"]["retry_policy"].get(v["id"], {"error": "missing"})
            row[impl] = fmt_retry(obs)
            if v["spec_status"] != "normative":
                continue
            ok = "error" not in obs and obs.get("decision") == expected["decision"]
            if ok and expected["decision"] == "Retry":
                ok = obs.get("delay_ms") == expected["delay_ms"]
            if not ok:
                mismatches.append({
                    "suite": "retry_policy", "id": v["id"], "impl": impl, "tags": v["tags"],
                    "input": {k: v[k] for k in ("status", "attempt", "max_retries", "retry_after")},
                    "expected": fmt_retry(expected), "actual": fmt_retry(obs),
                })
        if v["spec_status"] != "normative":
            ambiguous.append({"suite": "retry_policy", "id": v["id"], "tags": v["tags"], "observed": row})

    for v in doc["circuit_breaker"]:
        if v["spec_status"] != "normative":
            row = {impl: rep["results"]["circuit_breaker"].get(v["id"]) for impl, rep in reports.items()}
            ambiguous.append({"suite": "circuit_breaker", "id": v["id"], "tags": v["tags"], "observed": row})
            continue
        for impl, rep in reports.items():
            steps = rep["results"]["circuit_breaker"].get(v["id"], [])
            for i, step in enumerate(v["steps"]):
                obs = steps[i] if i < len(steps) else {"error": "missing"}
                diffs = {}
                for field, exp_val in step["expect"].items():
                    if obs.get(field) != exp_val:
                        diffs[field] = {"expected": exp_val, "actual": obs.get(field, obs.get("error"))}
                if diffs:
                    mismatches.append({
                        "suite": "circuit_breaker", "id": v["id"], "impl": impl, "tags": v["tags"],
                        "step": i, "op": step["op"], "t": step["t"], "diffs": diffs,
                    })
    return mismatches, numeric_boundaries, ambiguous


def counts(doc: dict) -> dict:
    return {
        "backoff": len(doc["backoff"]),
        "jitter": len(doc.get("jitter", [])),
        "retry_policy": sum(1 for v in doc["retry_policy"] if v["spec_status"] == "normative"),
        "circuit_breaker_steps": sum(
            len(v["steps"]) for v in doc["circuit_breaker"] if v["spec_status"] == "normative"
        ),
        "numeric_boundary": len(doc.get("backoff_numeric_boundary", [])),
    }


def print_report(doc, reports, mismatches, numeric_boundaries, ambiguous) -> None:
    total = counts(doc)
    per_impl_normative = (
        total["backoff"] + total["jitter"] + total["retry_policy"] + total["circuit_breaker_steps"]
    )
    print("\n=== SmoothAPI Differential Verification (Normative Common-Domain) ===")
    print(f"Normative vectors: {total['backoff']} backoff | {total['jitter']} jitter | "
          f"{total['retry_policy']} retry | {total['circuit_breaker_steps']} circuit steps "
          f"({per_impl_normative} checks/impl)\n")

    header = f"{'impl':<12} {'backoff':>10} {'jitter':>10} {'retry':>10} {'circuit':>10} {'total':>10}"
    print(header)
    print("-" * len(header))

    def failed(impl: str, suite: str) -> set:
        return {(m["id"], m.get("step")) for m in mismatches if m["impl"] == impl and m["suite"] == suite}

    for impl in reports:
        b = total["backoff"] - len(failed(impl, "backoff"))
        j = total["jitter"] - len(failed(impl, "jitter"))
        r = total["retry_policy"] - len(failed(impl, "retry_policy"))
        c = total["circuit_breaker_steps"] - len(failed(impl, "circuit_breaker"))
        t = b + j + r + c
        print(f"{impl:<12} {b:>4}/{total['backoff']:<5} {j:>4}/{total['jitter']:<5} "
              f"{r:>4}/{total['retry_policy']:<5} {c:>4}/{total['circuit_breaker_steps']:<5} "
              f"{t:>4}/{per_impl_normative:<5}")

    for impl, rep in reports.items():
        for note in rep.get("notes", []):
            print(f"  note[{impl}]: {note}")

    if mismatches:
        print(f"\n--- {len(mismatches)} normative mismatches ---")
        for m in mismatches:
            if m["suite"] == "backoff":
                lossy = " (input not representable)" if m["input_lossy"] else ""
                print(f"[backoff] {m['id']:<5} {m['impl']:<12} expected {m['expected']:<22} "
                      f"actual {m['actual']}{lossy}  {m['tags']}")
            elif m["suite"] == "jitter":
                print(f"[jitter]  {m['id']:<5} {m['impl']:<12} expected {m['expected']:<16} "
                      f"actual {m['actual']:<16} strategy={m['strategy']}  {m['tags']}")
            elif m["suite"] == "retry_policy":
                print(f"[retry]   {m['id']:<5} {m['impl']:<12} expected {m['expected']:<16} "
                      f"actual {m['actual']:<16} input={m['input']}")
            else:
                print(f"[circuit] {m['id']:<5} {m['impl']:<12} step {m['step']} {m['op']}@t={m['t']} "
                      f"diffs={m['diffs']}")
    else:
        print("\nNormative common-domain parity: 100% agreement across all 5 implementations.")

    if numeric_boundaries:
        print(f"\n=== Language Numeric Representation Boundaries ({len(numeric_boundaries)} vectors, recorded separately) ===")
        for nb in numeric_boundaries:
            print(f"[{nb['id']}] exact_u64={nb['exact_u64_ms']}  tags={nb['tags']}")
            for impl, info in nb["by_impl"].items():
                marker = "==" if info["matches_exact_u64"] else "!="
                lossy = " (lossy JS Number input)" if info["input_lossy"] else ""
                print(f"    {impl:<12} {marker} {info['observed']}{lossy}")

    if ambiguous:
        print("\n--- Exploratory / Ambiguous vectors (recorded, excluded from normative totals) ---")
        for a in ambiguous:
            print(f"[{a['suite']}] {a['id']} {a['tags']}")
            for impl, val in a["observed"].items():
                if isinstance(val, list):
                    val = val[-1] if val else val
                print(f"    {impl:<12} {val}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json-out", type=Path, help="Write the full report as JSON")
    parser.add_argument("--only", nargs="+", choices=IMPLS, help="Run a subset of implementations")
    args = parser.parse_args()

    doc = json.loads(VECTORS.read_text(encoding="utf-8"))
    problems = self_check(doc)
    if problems:
        print("Spec self-check FAILED: vectors disagree with the independent spec model:")
        for p in problems:
            print(f"  - {p}")
        return 2
    print("Spec self-check passed: expected values agree with the independent spec model.")

    reports = {}
    for impl in args.only or IMPLS:
        try:
            reports[impl] = run_impl(impl)
        except Exception as err:  # noqa: BLE001
            print(f"ERROR: {err}")
            return 2

    mismatches, numeric_boundaries, ambiguous = score(doc, reports)
    print_report(doc, reports, mismatches, numeric_boundaries, ambiguous)

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(
            {
                "counts": counts(doc),
                "reports": reports,
                "mismatches": mismatches,
                "numeric_boundaries": numeric_boundaries,
                "ambiguous": ambiguous,
            },
            indent=2,
        ), encoding="utf-8")
        print(f"\nFull report written to {args.json_out}")

    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
