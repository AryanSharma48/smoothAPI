import argparse
import json
import sys
import time
import types
from pathlib import Path

pkg_path = Path(__file__).resolve().parents[2] / "packages" / "smooth-api-py"
sys.path.insert(0, str(pkg_path))

import smoothapi_rs
from smooth_api import state as state_mod
from smooth_api.config import BackoffConfig, CircuitBreakerConfig
from smooth_api.utils import calculate_backoff

DEFAULT_RETRY_ON = [429, 500, 502, 503, 504]


def evaluate_response(status: int, attempt: int, config: BackoffConfig, retry_after: str | None):
    if 200 <= status < 400:
        return {"type": "Success"}
    if status not in DEFAULT_RETRY_ON:
        return {"type": "Terminal"}
    if attempt >= config.max_retries:
        return {"type": "Exhausted"}

    delay_s = calculate_backoff(attempt, config)
    if status == 429 and retry_after is not None:
        trimmed = retry_after.strip()
        if trimmed.isascii() and trimmed.isdigit():
            parsed = int(trimmed)
            if parsed >= 0:
                delay_s = float(parsed)
    return {"type": "Retry", "delay_ms": delay_s * 1000.0}


def verify_correctness(config: BackoffConfig, impl: str):
    expected_ms = [
        (0, 100),
        (1, 200),
        (2, 400),
        (3, 800),
        (10, 30000),
    ]
    for attempt, exp_ms in expected_ms:
        if impl == "py_pyo3":
            val_ms = smoothapi_rs.calculate_backoff_native(attempt, 100, 30000)
            assert val_ms == exp_ms, f"PyO3 backoff failed: attempt {attempt} got {val_ms}"
        else:
            val_s = calculate_backoff(attempt, config)
            assert abs(val_s * 1000.0 - exp_ms) < 1e-4, f"Python backoff failed: attempt {attempt}"

    if impl == "py_pyo3":
        assert smoothapi_rs.evaluate_response_native(200, 0, 100, 30000, 3, None).type == "Success"
        assert smoothapi_rs.evaluate_response_native(404, 0, 100, 30000, 3, None).type == "Terminal"
        d3 = smoothapi_rs.evaluate_response_native(503, 0, 100, 30000, 3, None)
        assert d3.type == "Retry" and d3.delay_ms == 100
        d4 = smoothapi_rs.evaluate_response_native(429, 0, 100, 30000, 3, "5")
        assert d4.type == "Retry" and d4.delay_ms == 5000
        assert smoothapi_rs.evaluate_response_native(500, 3, 100, 30000, 3, None).type == "Exhausted"
    else:
        assert evaluate_response(200, 0, config, None)["type"] == "Success"
        assert evaluate_response(404, 0, config, None)["type"] == "Terminal"
        d3 = evaluate_response(503, 0, config, None)
        assert d3["type"] == "Retry" and abs(d3["delay_ms"] - 100.0) < 1e-4
        d4 = evaluate_response(429, 0, config, "5")
        assert d4["type"] == "Retry" and abs(d4["delay_ms"] - 5000.0) < 1e-4
        assert evaluate_response(500, 3, config, None)["type"] == "Exhausted"


def bench_backoff(iterations: int, warmup: int, round_num: int, config: BackoffConfig, impl: str):
    attempts = (0, 1, 2, 3, 10)
    warmup_batches = max(1, warmup // 5)
    batches = max(1, iterations // 5)
    actual_iterations = batches * 5

    if impl == "py_pyo3":
        fn = smoothapi_rs.calculate_backoff_native
        sink = 0
        for _ in range(warmup_batches):
            for att in attempts:
                sink += fn(att, 100, 30000)

        start = time.perf_counter_ns()
        for _ in range(batches):
            for att in attempts:
                sink += fn(att, 100, 30000)
        end = time.perf_counter_ns()
    else:
        sink = 0.0
        for _ in range(warmup_batches):
            for att in attempts:
                sink += calculate_backoff(att, config)

        start = time.perf_counter_ns()
        for _ in range(batches):
            for att in attempts:
                sink += calculate_backoff(att, config)
        end = time.perf_counter_ns()

    elapsed_ns = end - start
    elapsed_ms = elapsed_ns / 1_000_000.0
    elapsed_sec = elapsed_ns / 1_000_000_000.0
    ops_per_sec = actual_iterations / elapsed_sec if elapsed_sec > 0 else 0.0
    ns_per_op = elapsed_ns / actual_iterations if actual_iterations > 0 else 0.0

    if sink == 0:
        print("Prevent DCE", file=sys.stderr)

    return {
        "workload": "backoff_deterministic",
        "language": impl,
        "round": round_num,
        "iterations": actual_iterations,
        "elapsed_ms": elapsed_ms,
        "ops_per_sec": ops_per_sec,
        "ns_per_op": ns_per_op,
    }


def bench_policy(iterations: int, warmup: int, round_num: int, config: BackoffConfig, impl: str):
    test_cases = (
        (200, 0, None),
        (404, 0, None),
        (503, 0, None),
        (429, 0, "5"),
        (500, 3, None),
    )
    warmup_batches = max(1, warmup // 5)
    batches = max(1, iterations // 5)
    actual_iterations = batches * 5

    if impl == "py_pyo3":
        fn = smoothapi_rs.evaluate_response_native
        sink = 0
        for _ in range(warmup_batches):
            for status, attempt, retry_after in test_cases:
                res = fn(status, attempt, 100, 30000, 3, retry_after)
                sink += res.delay_ms or 1

        start = time.perf_counter_ns()
        for _ in range(batches):
            for status, attempt, retry_after in test_cases:
                res = fn(status, attempt, 100, 30000, 3, retry_after)
                sink += res.delay_ms or 1
        end = time.perf_counter_ns()
    else:
        sink = 0.0
        for _ in range(warmup_batches):
            for status, attempt, retry_after in test_cases:
                res = evaluate_response(status, attempt, config, retry_after)
                sink += res.get("delay_ms", 1.0)

        start = time.perf_counter_ns()
        for _ in range(batches):
            for status, attempt, retry_after in test_cases:
                res = evaluate_response(status, attempt, config, retry_after)
                sink += res.get("delay_ms", 1.0)
        end = time.perf_counter_ns()

    elapsed_ns = end - start
    elapsed_ms = elapsed_ns / 1_000_000.0
    elapsed_sec = elapsed_ns / 1_000_000_000.0
    ops_per_sec = actual_iterations / elapsed_sec if elapsed_sec > 0 else 0.0
    ns_per_op = elapsed_ns / actual_iterations if actual_iterations > 0 else 0.0

    if sink == 0:
        print("Prevent DCE", file=sys.stderr)

    return {
        "workload": "retry_policy_evaluation",
        "language": impl,
        "round": round_num,
        "iterations": actual_iterations,
        "elapsed_ms": elapsed_ms,
        "ops_per_sec": ops_per_sec,
        "ns_per_op": ns_per_op,
    }


def bench_circuit(iterations: int, warmup: int, round_num: int, impl: str):
    warmup_batches = max(1, warmup // 5)
    batches = max(1, iterations // 5)
    actual_iterations = batches * 5
    sink = 0

    if impl == "py_pyo3":
        cb = smoothapi_rs.NativeCircuitBreaker(3, 5000)
        for _ in range(warmup_batches):
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

        start = time.perf_counter_ns()
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
        end = time.perf_counter_ns()
    else:
        clock = [0.0]
        real_time = state_mod.time
        state_mod.time = types.SimpleNamespace(time=lambda: clock[0])
        try:
            cb = state_mod.CircuitBreakerState(
                CircuitBreakerConfig(failure_threshold=3, cooldown_ms=5000)
            )
            key = "api.bench.local"
            for _ in range(warmup_batches):
                clock[0] = 1.0
                if cb.can_request(key):
                    sink += 1
                cb.record_failure(key)
                clock[0] = 2.0
                if cb.can_request(key):
                    sink += 1
                cb.record_failure(key)
                clock[0] = 3.0
                if cb.can_request(key):
                    sink += 1
                cb.record_failure(key)
                clock[0] = 5.0
                if not cb.can_request(key):
                    sink += 1
                clock[0] = 8.001
                if cb.can_request(key):
                    sink += 1
                cb.record_success(key)

            start = time.perf_counter_ns()
            for _ in range(batches):
                clock[0] = 1.0
                if cb.can_request(key):
                    sink += 1
                cb.record_failure(key)
                clock[0] = 2.0
                if cb.can_request(key):
                    sink += 1
                cb.record_failure(key)
                clock[0] = 3.0
                if cb.can_request(key):
                    sink += 1
                cb.record_failure(key)
                clock[0] = 5.0
                if not cb.can_request(key):
                    sink += 1
                clock[0] = 8.001
                if cb.can_request(key):
                    sink += 1
                cb.record_success(key)
            end = time.perf_counter_ns()
        finally:
            state_mod.time = real_time

    elapsed_ns = end - start
    elapsed_ms = elapsed_ns / 1_000_000.0
    elapsed_sec = elapsed_ns / 1_000_000_000.0
    ops_per_sec = actual_iterations / elapsed_sec if elapsed_sec > 0 else 0.0
    ns_per_op = elapsed_ns / actual_iterations if actual_iterations > 0 else 0.0

    if sink == 0:
        print("Prevent DCE", file=sys.stderr)

    return {
        "workload": "circuit_breaker_transitions",
        "language": impl,
        "round": round_num,
        "iterations": actual_iterations,
        "elapsed_ms": elapsed_ms,
        "ops_per_sec": ops_per_sec,
        "ns_per_op": ns_per_op,
    }


def py_noop(x: int) -> int:
    return x


def bench_noop(iterations: int, warmup: int, round_num: int, impl: str):
    inputs = (1, 2, 3, 4, 5)
    warmup_batches = max(1, warmup // 5)
    batches = max(1, iterations // 5)
    actual_iterations = batches * 5
    sink = 0

    if impl == "py_pyo3":
        fn = smoothapi_rs.noop_native
    elif impl == "py_pyo3_nogil":
        fn = smoothapi_rs.noop_nogil
    else:
        fn = py_noop

    for _ in range(warmup_batches):
        for x in inputs:
            sink += fn(x)

    start = time.perf_counter_ns()
    for _ in range(batches):
        for x in inputs:
            sink += fn(x)
    end = time.perf_counter_ns()

    elapsed_ns = end - start
    elapsed_ms = elapsed_ns / 1_000_000.0
    elapsed_sec = elapsed_ns / 1_000_000_000.0
    ops_per_sec = actual_iterations / elapsed_sec if elapsed_sec > 0 else 0.0
    ns_per_op = elapsed_ns / actual_iterations if actual_iterations > 0 else 0.0

    if sink == 0:
        print("Prevent DCE", file=sys.stderr)

    return {
        "workload": "noop_roundtrip",
        "language": impl,
        "round": round_num,
        "iterations": actual_iterations,
        "elapsed_ms": elapsed_ms,
        "ops_per_sec": ops_per_sec,
        "ns_per_op": ns_per_op,
    }


def main():
    parser = argparse.ArgumentParser(description="SmoothAPI Python Benchmark Runner")
    parser.add_argument("--workload", default="backoff_deterministic")
    parser.add_argument("--iterations", type=int, default=100000)
    parser.add_argument("--warmup", type=int, default=10000)
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--impl", default="python")
    args = parser.parse_args()

    config = BackoffConfig(
        base_delay=0.1,    # 100ms
        max_delay=30.0,    # 30,000ms
        max_retries=3,
        jitter="none",
    )

    if args.workload != "noop_roundtrip":
        verify_correctness(config, args.impl)

    if args.workload == "backoff_deterministic":
        result = bench_backoff(args.iterations, args.warmup, args.round, config, args.impl)
    elif args.workload == "retry_policy_evaluation":
        result = bench_policy(args.iterations, args.warmup, args.round, config, args.impl)
    elif args.workload == "circuit_breaker_transitions":
        result = bench_circuit(args.iterations, args.warmup, args.round, args.impl)
    elif args.workload == "noop_roundtrip":
        result = bench_noop(args.iterations, args.warmup, args.round, args.impl)
    else:
        print(f"Unknown workload: {args.workload}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
