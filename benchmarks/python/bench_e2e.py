"""End-to-End API Client Benchmark Runner (Native Python vs Python + PyO3).

Scenarios:
  1. normal_200            : 200 OK baseline request overhead
  2. intermittent_503_429  : 1st attempt fails (503/429 with Retry-After: 0), 2nd succeeds (200)
  3. repeated_failures_cb  : Persistent 503 trips circuit breaker after 3 failures; remaining
                             requests fast-fail in-process via OPEN circuit fallback
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import functools
import json
import math
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR / "packages" / "smooth-api-py"))

import requests
import smoothapi_rs
import threading
from smooth_api import (
    BackoffConfig,
    CircuitBreakerConfig,
    FailureContext,
    SmoothConfig,
    _extract_url,
    _resolve_circuit_key,
    _safe_invoke,
    smooth_api,
)
from smooth_api.utils import sleep_backoff


def get_process_memory_mb() -> tuple[float, float]:
    """Return (WorkingSetSize_MB, PrivatePagefileUsage_MB) on Windows with zero loop overhead."""
    if sys.platform == "win32":
        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        pmc = PROCESS_MEMORY_COUNTERS()
        pmc.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.windll.psapi
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        handle = k32.GetCurrentProcess()
        if psapi.GetProcessMemoryInfo(handle, ctypes.byref(pmc), pmc.cb):
            rss_mb = pmc.WorkingSetSize / (1024.0 * 1024.0)
            private_mb = pmc.PagefileUsage / (1024.0 * 1024.0)
            return rss_mb, private_mb
    return 0.0, 0.0


def create_pyo3_smooth_api(config: SmoothConfig):
    """Decorator equivalent to @smooth_api backed by smoothapi_rs (PyO3, GIL held)."""
    base_ms = int(round(config.backoff.base_delay * 1000.0))
    max_ms = int(round(config.backoff.max_delay * 1000.0))
    max_retries = config.backoff.max_retries
    jitter = config.backoff.jitter
    threshold = config.circuit_breaker.failure_threshold
    cooldown_ms = config.circuit_breaker.cooldown_ms
    fallback = config.fallback

    def decorator(fn):
        breaker = smoothapi_rs.NativeCircuitBreaker(threshold, cooldown_ms)

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            now_ms = int(time.time() * 1000.0)
            if not breaker.can_request(now_ms):
                if fallback is not None:
                    return fallback
                raise RuntimeError("Circuit breaker is OPEN")

            last_err = None
            prev_delay_ms = None
            try:
                for attempt in range(max_retries + 1):
                    try:
                        result = fn(*args, **kwargs)
                        breaker.record_success()
                        return result
                    except requests.HTTPError as err:
                        last_err = err
                        resp = err.response
                        status = resp.status_code if resp is not None else 500
                        retry_after = (
                            resp.headers.get("Retry-After")
                            if (resp is not None and status == 429)
                            else None
                        )
                        decision = smoothapi_rs.evaluate_response_native(
                            status,
                            attempt,
                            base_ms,
                            max_ms,
                            max_retries,
                            retry_after,
                        )
                        if decision.type == "Terminal":
                            raise
                        breaker.record_failure(int(time.time() * 1000.0))
                        if decision.type == "Retry":
                            delay_ms = decision.delay_ms or 0
                            if jitter != "none" and not (status == 429 and retry_after is not None):
                                import random
                                delay_ms = smoothapi_rs.calculate_backoff_native(
                                    attempt,
                                    base_ms,
                                    max_ms,
                                    jitter,
                                    prev_delay_ms,
                                    random.random(),
                                )
                            prev_delay_ms = delay_ms
                            sleep_backoff(delay_ms / 1000.0)
                            continue
                        return resp
                raise last_err  # type: ignore[misc]
            finally:
                breaker.release_probe()

        return wrapper

    return decorator


class Pyo3CircuitBreakerState:
    """Domain-keyed dict wrapper around smoothapi_rs.NativeCircuitBreaker matching CircuitBreakerState."""

    def __init__(self, config: CircuitBreakerConfig | None = None):
        self._config = config or CircuitBreakerConfig()
        self._map: dict[str, smoothapi_rs.NativeCircuitBreaker] = {}
        self._lock = threading.RLock()

    def _get_or_create(self, domain: str) -> smoothapi_rs.NativeCircuitBreaker:
        if domain not in self._map:
            if len(self._map) > 1000:
                keys_to_del = [k for k, v in self._map.items() if v.get_state() == "CLOSED"]
                for k in keys_to_del:
                    del self._map[k]
            self._map[domain] = smoothapi_rs.NativeCircuitBreaker(
                self._config.failure_threshold,
                self._config.cooldown_ms,
            )
        return self._map[domain]

    def can_request(self, domain: str) -> bool:
        now_ms = int(time.time() * 1000.0)
        with self._lock:
            entry = self._get_or_create(domain)
            return entry.can_request(now_ms)

    def record_success(self, domain: str) -> None:
        with self._lock:
            entry = self._get_or_create(domain)
            entry.record_success()

    def record_failure(self, domain: str) -> None:
        now_ms = int(time.time() * 1000.0)
        with self._lock:
            entry = self._get_or_create(domain)
            entry.record_failure(now_ms)

    def release_probe(self, domain: str) -> None:
        with self._lock:
            if domain in self._map:
                self._map[domain].release_probe()


def create_fair_pyo3_smooth_api(config: SmoothConfig):
    """Decorator executing identical URL/key/dict/config pre-work as @smooth_api, differing only in PyO3 breaker."""
    base_ms = int(round(config.backoff.base_delay * 1000.0))
    max_ms = int(round(config.backoff.max_delay * 1000.0))
    max_retries = config.backoff.max_retries
    jitter = config.backoff.jitter

    def decorator(fn):
        breaker = Pyo3CircuitBreakerState(config.circuit_breaker)
        domain = fn.__qualname__

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            url = _extract_url(args, kwargs)
            fallback = kwargs.pop("fallback", config.fallback)
            key = _resolve_circuit_key(domain, url, args, kwargs, config.circuit_breaker)

            if not breaker.can_request(key):
                if config.on_failure:
                    _safe_invoke(
                        config.on_failure,
                        FailureContext(
                            url=url,
                            domain=key,
                            attempts=0,
                            duration_ms=(time.perf_counter() - start_time) * 1000.0,
                            error=RuntimeError(f"Circuit breaker is OPEN for: {key}"),
                            is_circuit_open=True,
                        ),
                    )
                if fallback is not None:
                    return fallback
                raise RuntimeError(f"Circuit breaker is OPEN for: {key}")

            last_err = None
            prev_delay_ms = None
            try:
                for attempt in range(max_retries + 1):
                    try:
                        result = fn(*args, **kwargs)
                        breaker.record_success(key)
                        return result
                    except requests.HTTPError as err:
                        last_err = err
                        resp = err.response
                        status = resp.status_code if resp is not None else 500
                        retry_after = (
                            resp.headers.get("Retry-After")
                            if (resp is not None and status == 429)
                            else None
                        )
                        decision = smoothapi_rs.evaluate_response_native(
                            status,
                            attempt,
                            base_ms,
                            max_ms,
                            max_retries,
                            retry_after,
                        )
                        if decision.type == "Terminal":
                            raise
                        breaker.record_failure(key)
                        if decision.type == "Retry":
                            delay_ms = decision.delay_ms or 0
                            if jitter != "none" and not (status == 429 and retry_after is not None):
                                import random
                                delay_ms = smoothapi_rs.calculate_backoff_native(
                                    attempt,
                                    base_ms,
                                    max_ms,
                                    jitter,
                                    prev_delay_ms,
                                    random.random(),
                                )
                            prev_delay_ms = delay_ms
                            sleep_backoff(delay_ms / 1000.0)
                            continue
                        return resp
                raise last_err  # type: ignore[misc]
            finally:
                breaker.release_probe(key)

        return wrapper

    return decorator


def percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, max(0, math.ceil((p / 100.0) * len(sorted_vals)) - 1))
    return sorted_vals[idx]


def run_scenario(
    impl: str,
    scenario: str,
    base_url: str,
    num_requests: int,
    warmup: int,
    round_num: int,
    fair: bool = False,
) -> dict:
    session = requests.Session()
    if impl == "py_pyo3":
        deco_factory = create_fair_pyo3_smooth_api if fair else create_pyo3_smooth_api
    else:
        deco_factory = smooth_api

    if scenario == "normal_200":
        cfg = SmoothConfig(
            backoff=BackoffConfig(base_delay=0.001, max_delay=0.1, max_retries=2, jitter="none"),
            circuit_breaker=CircuitBreakerConfig(failure_threshold=1_000_000, cooldown_ms=60_000),
        )
    elif scenario == "intermittent_503_429":
        cfg = SmoothConfig(
            backoff=BackoffConfig(base_delay=0.001, max_delay=0.1, max_retries=2, jitter="none"),
            circuit_breaker=CircuitBreakerConfig(failure_threshold=1_000_000, cooldown_ms=60_000),
        )
    elif scenario == "repeated_failures_cb":
        cfg = SmoothConfig(
            backoff=BackoffConfig(base_delay=0.001, max_delay=0.1, max_retries=0, jitter="none"),
            circuit_breaker=CircuitBreakerConfig(failure_threshold=3, cooldown_ms=600_000),
            fallback={"fallback": True},
        )
    else:
        raise ValueError(f"Unknown scenario: {scenario}")

    def make_client():
        @deco_factory(cfg)
        def fetch_endpoint(url: str):
            r = session.get(url)
            r.raise_for_status()
            return r

        return fetch_endpoint

    # Warm-up with a separate decorated client
    warmup_client = make_client()
    for i in range(warmup):
        warmup_client(f"{base_url}/{scenario}?id=w_{i}")

    # Timed phase with a fresh decorated client
    client = make_client()
    latencies_ms: list[float] = [0.0] * num_requests

    rss_before, priv_before = get_process_memory_mb()
    cpu_start = time.process_time()
    wall_start = time.perf_counter_ns()

    for i in range(num_requests):
        t0 = time.perf_counter_ns()
        client(f"{base_url}/{scenario}?id={round_num}_{i}")
        t1 = time.perf_counter_ns()
        latencies_ms[i] = (t1 - t0) / 1_000_000.0

    wall_end = time.perf_counter_ns()
    cpu_end = time.process_time()
    rss_after, priv_after = get_process_memory_mb()
    session.close()

    elapsed_ms = (wall_end - wall_start) / 1_000_000.0
    req_per_sec = num_requests / (elapsed_ms / 1000.0)
    cpu_ms = (cpu_end - cpu_start) * 1000.0
    cpu_ms_per_1k = (cpu_ms / num_requests) * 1000.0
    cpu_pct = (cpu_ms / elapsed_ms) * 100.0 if elapsed_ms > 0 else 0.0
    rss_mb = max(rss_before, rss_after)
    heap_mb = max(priv_before, priv_after)

    sorted_lats = sorted(latencies_ms)
    mean_ms = sum(sorted_lats) / len(sorted_lats)

    return {
        "scenario": scenario,
        "impl": impl,
        "round": round_num,
        "requests": num_requests,
        "elapsed_ms": round(elapsed_ms, 4),
        "req_per_sec": round(req_per_sec, 2),
        "mean_ms": round(mean_ms, 4),
        "p50_ms": round(percentile(sorted_lats, 50), 4),
        "p95_ms": round(percentile(sorted_lats, 95), 4),
        "p99_ms": round(percentile(sorted_lats, 99), 4),
        "cpu_ms": round(cpu_ms, 4),
        "cpu_ms_per_1k_reqs": round(cpu_ms_per_1k, 4),
        "cpu_pct": round(cpu_pct, 2),
        "rss_mb": round(rss_mb, 2),
        "heap_mb": round(heap_mb, 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--impl", choices=["py_native", "py_pyo3"], default="py_native")
    parser.add_argument("--scenario", default="normal_200")
    parser.add_argument("--url", default="http://127.0.0.1:3099")
    parser.add_argument("--requests", type=int, default=500)
    parser.add_argument("--warmup", type=int, default=50)
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--fair", action="store_true")
    args = parser.parse_args()

    res = run_scenario(
        args.impl,
        args.scenario,
        args.url,
        args.requests,
        args.warmup,
        args.round,
        fair=args.fair,
    )
    print(json.dumps(res))


if __name__ == "__main__":
    main()
