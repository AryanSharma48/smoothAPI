import pytest
from smooth_api import resilient_api, SmoothConfig, ResilientConfig


def test_resilient_api_warning():
    with pytest.warns(DeprecationWarning, match="resilient_api"):
        resilient_api(SmoothConfig())


def test_resilient_config_warning():
    with pytest.warns(DeprecationWarning, match="ResilientConfig"):
        ResilientConfig()