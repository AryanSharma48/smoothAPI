import pytest
import threading

def test_calculate_backoff_native():
    from smoothapi_rs import calculate_backoff_native

    # Expected: attempt 0: 100ms, attempt 1: 200ms, attempt 2: 400ms, attempt 3: 800ms
    assert calculate_backoff_native(0, 100, 30000) == 100
    assert calculate_backoff_native(1, 100, 30000) == 200
    assert calculate_backoff_native(2, 100, 30000) == 400
    assert calculate_backoff_native(3, 100, 30000) == 800

    # Capped at max_delay_ms
    assert calculate_backoff_native(10, 100, 30000) == 30000


def test_evaluate_response_native_success():
    from smoothapi_rs import evaluate_response_native

    decision = evaluate_response_native(200, 0, 100, 30000)
    assert decision.type == "Success"
    assert decision.delay_ms is None


def test_evaluate_response_native_terminal():
    from smoothapi_rs import evaluate_response_native

    # 404 is client error, not retryable
    decision = evaluate_response_native(404, 0, 100, 30000)
    assert decision.type == "Terminal"
    assert decision.delay_ms is None


def test_evaluate_response_native_retryable():
    from smoothapi_rs import evaluate_response_native

    # 503 at attempt 0
    decision = evaluate_response_native(503, 0, 100, 30000)
    assert decision.type == "Retry"
    assert decision.delay_ms == 100


def test_evaluate_response_native_retry_after():
    from smoothapi_rs import evaluate_response_native

    # 429 with Retry-After header "5" -> 5000ms
    decision = evaluate_response_native(429, 0, 100, 30000, 3, "5")
    assert decision.type == "Retry"
    assert decision.delay_ms == 5000

    # 429 with Retry-After header "0" -> 0ms (RFC 9110 valid non-negative integer)
    zero_decision = evaluate_response_native(429, 0, 100, 30000, 3, "0")
    assert zero_decision.type == "Retry"
    assert zero_decision.delay_ms == 0


def test_calculate_backoff_native_jitter():
    from smoothapi_rs import calculate_backoff_native

    # Attempt 2: capped = 400ms
    assert calculate_backoff_native(2, 100, 1000, "none", None, 0.5) == 400
    assert calculate_backoff_native(2, 100, 1000, "full", None, 0.5) == 200
    assert calculate_backoff_native(2, 100, 1000, "equal", None, 0.5) == 300
    assert calculate_backoff_native(1, 100, 1000, "decorrelated", 200, 0.5) == 350
    assert calculate_backoff_native(2, 100, 1000, "default", None, 0.5) == 300



def test_evaluate_response_native_exhausted():
    from smoothapi_rs import evaluate_response_native

    # attempt 3 >= max_retries (3)
    decision = evaluate_response_native(500, 3, 100, 30000, 3)
    assert decision.type == "Exhausted"
    assert decision.delay_ms is None


def test_circuit_breaker_lifecycle():
    from smoothapi_rs import NativeCircuitBreaker

    cb = NativeCircuitBreaker(failure_threshold=3, cooldown_ms=5000)
    assert cb.state == "CLOSED"
    assert cb.failure_count == 0
    assert cb.can_request(1000) is True

    # 1st failure
    cb.record_failure(1000)
    assert cb.state == "CLOSED"
    assert cb.failure_count == 1

    # 2nd failure
    cb.record_failure(2000)
    assert cb.state == "CLOSED"
    assert cb.failure_count == 2

    # 3rd failure -> trips to OPEN
    cb.record_failure(3000)
    assert cb.state == "OPEN"
    assert cb.failure_count == 3

    # Cooldown has not passed (3000 + 5000 = 8000)
    assert cb.can_request(5000) is False

    # Cooldown expired at now_ms = 8001 -> transitions to HALF_OPEN
    assert cb.can_request(8001) is True
    assert cb.state == "HALF_OPEN"

    # Successful probe restores to CLOSED
    cb.record_success()
    assert cb.state == "CLOSED"
    assert cb.failure_count == 0


def test_circuit_breaker_half_open_failure_re_trips():
    from smoothapi_rs import NativeCircuitBreaker

    cb = NativeCircuitBreaker(failure_threshold=2, cooldown_ms=1000)
    cb.record_failure(100)
    cb.record_failure(200)
    assert cb.state == "OPEN"

    # Cooldown expires -> HALF_OPEN
    assert cb.can_request(1300) is True
    assert cb.state == "HALF_OPEN"

    # Probe fails -> immediately re-trips to OPEN
    cb.record_failure(1305)
    assert cb.state == "OPEN"
    assert cb.can_request(1400) is False


def test_circuit_breaker_probe_recovery():
    from smoothapi_rs import NativeCircuitBreaker

    cb = NativeCircuitBreaker(failure_threshold=1, cooldown_ms=1000)
    cb.record_failure(100)
    assert cb.state == "OPEN"

    # Cooldown boundary: 1099 (False), 1100 (False), 1101 (True -> HALF_OPEN)
    assert cb.can_request(1099) is False
    assert cb.can_request(1100) is False
    assert cb.can_request(1101) is True
    assert cb.state == "HALF_OPEN"

    # Second concurrent request while probe in flight is blocked
    assert cb.can_request(1200) is False

    # Explicit release_probe allows immediate retry
    cb.release_probe()
    assert cb.can_request(1300) is True

    # Abandoned probe recovers after lease expiry (> 1300 + 1000 = 2300)
    assert cb.can_request(2300) is False
    assert cb.can_request(2301) is True
    cb.record_success()
    assert cb.state == "CLOSED"



def test_circuit_breaker_thread_safety():
    from smoothapi_rs import NativeCircuitBreaker

    cb = NativeCircuitBreaker(failure_threshold=1000, cooldown_ms=5000)

    def worker():
        for i in range(100):
            cb.record_failure(i)
            _ = cb.can_request(i)
            _ = cb.state
            _ = cb.failure_count

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert cb.failure_count == 1000

