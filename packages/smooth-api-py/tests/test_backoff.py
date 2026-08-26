"""Unit tests for backoff and jitter calculation in smooth_api."""
import pytest
from smooth_api.config import BackoffConfig
from smooth_api.utils import calculate_backoff

def test_backoff_respects_max_delay_boundaries():
    config = BackoffConfig(base_delay=0.1, max_delay=5.0, max_retries=5)
    for _ in range(100):
        delay = calculate_backoff(10, config)
        assert 0.0 <= delay <= 5.0

def test_backoff_exhibits_jitter_distribution():
    config = BackoffConfig(base_delay=0.1, max_delay=5.0, max_retries=3)
    delays = set()
    for _ in range(20):
        delay = calculate_backoff(2, config)
        assert 0.0 <= delay <= 0.4
        delays.add(delay)
    
    assert len(delays) > 1, "Backoff jitter did not produce variable delays"
