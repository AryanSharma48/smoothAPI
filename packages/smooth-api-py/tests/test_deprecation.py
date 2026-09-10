import pytest
from smooth_api import resilient_api, SmoothConfig, ResilientConfig


def test_resilient_api_warning():
    with pytest.warns(DeprecationWarning, match="resilient_api"):
        resilient_api(SmoothConfig())


def test_resilient_config_warning():
    with pytest.warns(DeprecationWarning, match="ResilientConfig"):
        ResilientConfig()


def test_smooth_api_async_no_iscoroutinefunction_deprecation():
    import warnings
    from smooth_api import smooth_api

    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")

        @smooth_api(SmoothConfig())
        async def dummy_coro():
            return 42

    coro_warnings = [
        w
        for w in recorded
        if issubclass(w.category, DeprecationWarning)
        and "iscoroutinefunction" in str(w.message)
    ]
    assert len(coro_warnings) == 0