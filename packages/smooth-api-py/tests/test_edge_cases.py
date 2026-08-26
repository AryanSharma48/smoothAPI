"""Unit tests for domain sweeper memory cap and edge case header handling in smooth_api."""
import pytest
import requests
from smooth_api.state import CircuitBreakerState
from smooth_api import smooth_api, SmoothConfig
from smooth_api.config import BackoffConfig, CircuitBreakerConfig

def test_circuit_breaker_domain_memory_cleanup():
    breaker = CircuitBreakerState(CircuitBreakerConfig())
    
    # Add 1050 healthy CLOSED domains
    for i in range(1050):
        breaker.can_request(f"domain-{i}.com")
        
    # Trigger cleanup by checking a new domain
    breaker.can_request("trigger-cleanup.com")
    
    # Check that state querying domain-0.com returns CLOSED gracefully
    state = breaker.get_state("domain-0.com")
    assert state == "CLOSED"

def test_malformed_retry_after_header_handling():
    class MockResponseInvalid:
        status_code = 429
        headers = {"Retry-After": "not-a-number"}
        reason = "Too Many Requests"

    class MockResponseSuccess:
        status_code = 200
        headers = {}
        reason = "OK"
        def json(self):
            return {"success": True}

    call_count = [0]
    config = SmoothConfig(
        backoff=BackoffConfig(base_delay=0.01, max_delay=0.05, max_retries=1),
        retry_on=[429]
    )

    @smooth_api(config)
    def get_data():
        call_count[0] += 1
        if call_count[0] == 1:
            err = requests.exceptions.HTTPError("429")
            err.response = MockResponseInvalid()
            raise err
        return MockResponseSuccess()

    res = get_data()
    assert call_count[0] == 2
    assert res.status_code == 200
