"""Differential runner: Native Python and Python -> PyO3 -> Rust.

Usage: python benchmarks/tests/test_python_differential.py --impl py_native|py_pyo3 [vectors.json]

Native Python exercises PRODUCTION code paths only:
  - backoff:      smooth_api.utils.calculate_backoff. The package has no 'none' jitter
                  mode; it always applies full jitter (random.uniform(0, capped)). The
                  deterministic component is isolated by pinning uniform() to its upper
                  bound, which yields exactly `capped`. This is recorded in the output.
  - retry policy: the @smooth_api sync decorator driven by mocked requests.Response
                  objects; decisions are read from public hooks and return/raise behaviour.
  - circuit:      CircuitBreakerState with an injected time.time clock (ms / 1000).
No production source is modified; functions are patched only inside this process.

Outputs raw observations as JSON. Scoring happens in scripts/run_differential.py.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import types
from pathlib import Path
from typing import ClassVar

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "smooth-api-py"))


def to_decimal(value) -> str:
    """Render a numeric result without hiding float drift."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return repr(value)
        if value.is_integer():
            return str(int(value))
        return repr(value)
    return str(value)


# ── Native Python adapter ──────────────────────────────────────────────────────
class NativeAdapter:
    notes: ClassVar[list[str]] = [
        "py_native computes in float seconds; inputs are converted ms/1000 and outputs *1000.",
    ]

    def __init__(self):
        import requests
        import smooth_api
        from smooth_api import state, utils
        from smooth_api.config import BackoffConfig, CircuitBreakerConfig, SmoothConfig

        self.requests = requests
        self.smooth_api = smooth_api
        self.utils = utils
        self.state_mod = state
        self.BackoffConfig = BackoffConfig
        self.CircuitBreakerConfig = CircuitBreakerConfig
        self.SmoothConfig = SmoothConfig

    def backoff(self, base: int, max_: int, attempt: int):
        cfg = self.BackoffConfig(
            base_delay=base / 1000, max_delay=max_ / 1000, max_retries=3, jitter="none"
        )
        return self.utils.calculate_backoff(attempt, cfg) * 1000

    def jitter(self, v: dict):
        base = int(v["base_delay_ms"]) / 1000
        max_ = int(v["max_delay_ms"]) / 1000
        prev = int(v["prev_delay_ms"]) / 1000 if v["prev_delay_ms"] is not None else None
        if v["strategy"] == "default":
            cfg = self.BackoffConfig(base_delay=base, max_delay=max_, max_retries=3)
        else:
            cfg = self.BackoffConfig(
                base_delay=base, max_delay=max_, max_retries=3, jitter=v["strategy"]
            )
        delay_s = self.utils.calculate_backoff(
            v["attempt"], cfg, prev, float(v["random_factor"])
        )
        return int(math.floor(delay_s * 1000.0 + 1e-9))

    def _response(self, status: int, retry_after):
        r = self.requests.Response()
        r.status_code = status
        r.url = "http://diff.test/"
        r.reason = "diff"
        if retry_after is not None:
            r.headers["Retry-After"] = retry_after
        return r

    def retry(self, vec: dict, cfg: dict) -> dict:
        sequence = [(503, None)] * vec["attempt"] + [(vec["status"], vec["retry_after"])]
        calls = {"n": 0}
        events = {"retries": [], "success": None, "failure": None}

        def target():
            spec = sequence[min(calls["n"], len(sequence) - 1)]
            calls["n"] += 1
            resp = self._response(*spec)
            resp.raise_for_status()
            return resp

        config = self.SmoothConfig(
            backoff=self.BackoffConfig(
                base_delay=int(cfg["base_delay_ms"]) / 1000,
                max_delay=int(cfg["max_delay_ms"]) / 1000,
                max_retries=vec["max_retries"],
                jitter="none",
            ),
            circuit_breaker=self.CircuitBreakerConfig(failure_threshold=1_000_000),
            on_retry=lambda ctx: events["retries"].append(ctx),
            on_success=lambda ctx: events.__setitem__("success", ctx),
            on_failure=lambda ctx: events.__setitem__("failure", ctx),
        )
        target.__qualname__ = f"diff_{vec['id']}"

        real_sleep = self.smooth_api.sleep_backoff
        self.smooth_api.sleep_backoff = lambda seconds: None
        raised = None
        try:
            wrapped = self.smooth_api.smooth_api(config)(target)
            try:
                wrapped()
            except Exception as err:  # noqa: BLE001 - raising is an observable outcome
                raised = type(err).__name__
        finally:
            self.smooth_api.sleep_backoff = real_sleep

        raw = {
            "fetch_calls": calls["n"],
            "on_success": events["success"] is not None,
            "raised": raised,
        }
        match = [r for r in events["retries"] if r.attempt == vec["attempt"] + 1]
        if match:
            return {"decision": "Retry", "delay_ms": to_decimal(match[0].delay_ms), "raw": raw}
        if events["success"] is not None:
            return {"decision": "Success", "raw": raw}
        if events["failure"] is not None and raised is None:
            # Retryable status with retries exhausted: hook fires and the response is returned.
            return {"decision": "Exhausted", "raw": raw}
        if events["failure"] is not None and raised is not None:
            # Non-retryable status: hook fires and the HTTP error propagates.
            return {"decision": "Terminal", "raw": raw}
        return {"decision": "Unobserved", "raw": raw}

    def circuit(self, vec: dict) -> list:
        clock = {"ms": 0}
        real_time = self.state_mod.time
        self.state_mod.time = types.SimpleNamespace(time=lambda: clock["ms"] / 1000)
        try:
            cb = self.state_mod.CircuitBreakerState(
                self.CircuitBreakerConfig(
                    failure_threshold=vec["failure_threshold"], cooldown_ms=vec["cooldown_ms"]
                )
            )
            key = "diff.test"
            out = []
            for step in vec["steps"]:
                clock["ms"] = step["t"]
                obs = {}
                if step["op"] == "record_failure":
                    cb.record_failure(key)
                elif step["op"] == "record_success":
                    cb.record_success(key)
                elif step["op"] == "release_probe":
                    cb.release_probe(key)
                elif step["op"] == "can_request":
                    obs["ret"] = cb.can_request(key)
                stats = cb.get_stats(key)
                obs["state"] = cb.get_stored_state(key)
                obs["state_at"] = cb.get_state_at(key, step["t"])
                obs["failure_count"] = stats["failure_count"]
                out.append(obs)
            return out
        finally:
            self.state_mod.time = real_time


# ── PyO3 adapter ───────────────────────────────────────────────────────────────
class PyO3Adapter:
    notes: ClassVar[list[str]] = []

    def __init__(self):
        import smoothapi_rs

        self.native = smoothapi_rs

    def backoff(self, base: int, max_: int, attempt: int):
        return self.native.calculate_backoff_native(attempt, base, max_)

    def jitter(self, v: dict):
        prev = int(v["prev_delay_ms"]) if v["prev_delay_ms"] is not None else None
        return self.native.calculate_backoff_native(
            v["attempt"],
            int(v["base_delay_ms"]),
            int(v["max_delay_ms"]),
            v["strategy"],
            prev,
            float(v["random_factor"]),
        )

    def retry(self, vec: dict, cfg: dict) -> dict:
        d = self.native.evaluate_response_native(
            vec["status"],
            vec["attempt"],
            int(cfg["base_delay_ms"]),
            int(cfg["max_delay_ms"]),
            vec["max_retries"],
            vec["retry_after"],
        )
        if d.type == "Retry":
            return {"decision": d.type, "delay_ms": to_decimal(d.delay_ms)}
        return {"decision": d.type}

    def circuit(self, vec: dict) -> list:
        cb = self.native.NativeCircuitBreaker(vec["failure_threshold"], vec["cooldown_ms"])
        out = []
        for step in vec["steps"]:
            obs = {}
            if step["op"] == "record_failure":
                cb.record_failure(step["t"])
            elif step["op"] == "record_success":
                cb.record_success()
            elif step["op"] == "release_probe":
                cb.release_probe()
            elif step["op"] == "can_request":
                obs["ret"] = cb.can_request(step["t"])
            obs["state"] = cb.state
            obs["state_at"] = cb.state_at(step["t"])
            obs["failure_count"] = cb.failure_count
            out.append(obs)
        return out


def _run_backoff_list(adapter, items: list[dict]) -> dict:
    out = {}
    for v in items:
        try:
            val = adapter.backoff(int(v["base_delay_ms"]), int(v["max_delay_ms"]), v["attempt"])
            out[v["id"]] = {"value": to_decimal(val)}
        except Exception as err:  # noqa: BLE001 - errors are recorded as observations
            out[v["id"]] = {"error": f"{type(err).__name__}: {err}"}
    return out


def _run_jitter_list(adapter, items: list[dict]) -> dict:
    out = {}
    for v in items:
        try:
            val = adapter.jitter(v)
            out[v["id"]] = {"value": to_decimal(val)}
        except Exception as err:  # noqa: BLE001
            out[v["id"]] = {"error": f"{type(err).__name__}: {err}"}
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--impl", choices=["py_native", "py_pyo3"], default="py_native")
    parser.add_argument(
        "vectors", nargs="?", default=str(ROOT / "benchmarks" / "config" / "differential_vectors.json")
    )
    args = parser.parse_args()
    doc = json.loads(Path(args.vectors).read_text(encoding="utf-8"))

    adapter = NativeAdapter() if args.impl == "py_native" else PyO3Adapter()
    results: dict = {
        "backoff": _run_backoff_list(adapter, doc["backoff"]),
        "jitter": _run_jitter_list(adapter, doc.get("jitter", [])),
        "backoff_numeric_boundary": _run_backoff_list(
            adapter, doc.get("backoff_numeric_boundary", [])
        ),
        "retry_policy": {},
        "circuit_breaker": {},
    }

    for v in doc["retry_policy"]:
        try:
            results["retry_policy"][v["id"]] = adapter.retry(v, doc["retry_policy_config"])
        except Exception as err:  # noqa: BLE001
            results["retry_policy"][v["id"]] = {"error": f"{type(err).__name__}: {err}"}

    for v in doc["circuit_breaker"]:
        try:
            results["circuit_breaker"][v["id"]] = adapter.circuit(v)
        except Exception as err:  # noqa: BLE001
            results["circuit_breaker"][v["id"]] = [{"error": f"{type(err).__name__}: {err}"}]

    print(json.dumps({"impl": args.impl, "notes": adapter.notes, "results": results}))


if __name__ == "__main__":
    main()
