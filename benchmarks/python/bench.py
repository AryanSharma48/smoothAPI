import argparse
import json
import sys
import time
from pathlib import Path

# Add python package to sys.path
pkg_path = Path(__file__).resolve().parents[2] / "packages" / "smooth-api-py"
sys.path.insert(0, str(pkg_path))

from smooth_api.config import BackoffConfig

DEFAULT_RETRY_ON = [429, 500, 502, 503, 504]

def calculate_backoff_deterministic(attempt: int, config: BackoffConfig) -> float:
    # Deterministic exponential backoff matching jitter: none
    exponential = config.base_delay * (2 ** attempt)
    return min(config.max_delay, exponential)

def evaluate_response(status: int, attempt: int, config: BackoffConfig, retry_after: str | None):
    if 200 <= status < 300:
        return {"type": "Success"}
    if status not in DEFAULT_RETRY_ON:
        return {"type": "Terminal"}
    if attempt >= config.max_retries:
        return {"type": "Exhausted"}
    
    delay_s = calculate_backoff_deterministic(attempt, config)
    if status == 429 and retry_after:
        try:
            parsed = int(retry_after)
            if parsed > 0:
                delay_s = float(parsed)
        except ValueError:
            pass
    return {"type": "Retry", "delay_ms": delay_s * 1000.0}

def verify_correctness(config: BackoffConfig):
    # Expected values in seconds: 100ms -> 0.1s, 200ms -> 0.2s, etc.
    expected = [
        (0, 0.1),
        (1, 0.2),
        (2, 0.4),
        (3, 0.8),
        (10, 30.0),
    ]
    for attempt, exp in expected:
        val = calculate_backoff_deterministic(attempt, config)
        assert abs(val - exp) < 1e-6, f"Python backoff failed: attempt {attempt} got {val}, expected {exp}"

    d1 = evaluate_response(200, 0, config, None)
    assert d1["type"] == "Success", "Python correctness failed on 200"

    d2 = evaluate_response(404, 0, config, None)
    assert d2["type"] == "Terminal", "Python correctness failed on 404"

    d3 = evaluate_response(503, 0, config, None)
    assert d3["type"] == "Retry" and abs(d3["delay_ms"] - 100.0) < 1e-4, "Python correctness failed on 503"

    d4 = evaluate_response(429, 0, config, "5")
    assert d4["type"] == "Retry" and abs(d4["delay_ms"] - 5000.0) < 1e-4, "Python correctness failed on 429"

    d5 = evaluate_response(500, 3, config, None)
    assert d5["type"] == "Exhausted", "Python correctness failed on 500 exhausted"

def bench_backoff(iterations: int, warmup: int, round_num: int, config: BackoffConfig):
    attempts = [0, 1, 2, 3, 10]
    num_attempts = len(attempts)
    sink = 0.0

    # Warm-up (measurement control)
    for i in range(warmup):
        sink += calculate_backoff_deterministic(attempts[i % num_attempts], config)

    # Timed execution
    start = time.perf_counter_ns()
    for i in range(iterations):
        sink += calculate_backoff_deterministic(attempts[i % num_attempts], config)
    end = time.perf_counter_ns()

    elapsed_ns = end - start
    elapsed_ms = elapsed_ns / 1_000_000.0
    elapsed_sec = elapsed_ns / 1_000_000_000.0
    ops_per_sec = iterations / elapsed_sec if elapsed_sec > 0 else 0.0
    ns_per_op = elapsed_ns / iterations if iterations > 0 else 0.0

    if sink == 0.0:
        print("Prevent DCE", file=sys.stderr)

    return {
        "workload": "backoff_deterministic",
        "language": "python",
        "round": round_num,
        "iterations": iterations,
        "elapsed_ms": elapsed_ms,
        "ops_per_sec": ops_per_sec,
        "ns_per_op": ns_per_op,
    }

def bench_policy(iterations: int, warmup: int, round_num: int, config: BackoffConfig):
    test_cases = [
        (200, 0, None),
        (404, 0, None),
        (503, 0, None),
        (429, 0, "5"),
        (500, 3, None),
    ]
    num_cases = len(test_cases)
    sink = 0.0

    # Warm-up
    for i in range(warmup):
        c = test_cases[i % num_cases]
        res = evaluate_response(c[0], c[1], config, c[2])
        sink += res.get("delay_ms", 1.0)

    # Timed execution
    start = time.perf_counter_ns()
    for i in range(iterations):
        c = test_cases[i % num_cases]
        res = evaluate_response(c[0], c[1], config, c[2])
        sink += res.get("delay_ms", 1.0)
    end = time.perf_counter_ns()

    elapsed_ns = end - start
    elapsed_ms = elapsed_ns / 1_000_000.0
    elapsed_sec = elapsed_ns / 1_000_000_000.0
    ops_per_sec = iterations / elapsed_sec if elapsed_sec > 0 else 0.0
    ns_per_op = elapsed_ns / iterations if iterations > 0 else 0.0

    if sink == 0.0:
        print("Prevent DCE", file=sys.stderr)

    return {
        "workload": "retry_policy_evaluation",
        "language": "python",
        "round": round_num,
        "iterations": iterations,
        "elapsed_ms": elapsed_ms,
        "ops_per_sec": ops_per_sec,
        "ns_per_op": ns_per_op,
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workload", default="backoff_deterministic")
    parser.add_argument("--iterations", type=int, default=100000)
    parser.add_argument("--warmup", type=int, default=10000)
    parser.add_argument("--round", type=int, default=1)
    args = parser.parse_args()

    # Python base config in seconds (0.1s = 100ms, 30.0s = 30000ms)
    config = BackoffConfig(base_delay=0.1, max_delay=30.0, max_retries=3)

    verify_correctness(config)

    if args.workload == "backoff_deterministic":
        res = bench_backoff(args.iterations, args.warmup, args.round, config)
    elif args.workload == "retry_policy_evaluation":
        res = bench_policy(args.iterations, args.warmup, args.round, config)
    else:
        print(f"Unknown workload: {args.workload}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(res))

if __name__ == "__main__":
    main()
