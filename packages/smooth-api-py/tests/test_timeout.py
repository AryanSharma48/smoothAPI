import asyncio
import pytest
from smooth_api import smooth_api, SmoothConfig
from smooth_api.config import BackoffConfig

@pytest.mark.asyncio
async def test_async_timeout_aborts_and_retries():
    call_count = 0

    @smooth_api(SmoothConfig(
        timeout_ms=100,
        backoff=BackoffConfig(max_retries=1, base_delay=0.01)
    ))
    async def fetch_data():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            await asyncio.sleep(0.5)  # Should timeout
            return "delayed"
        return "success"
    
    result = await fetch_data()
    assert result == "success"
    assert call_count == 2

def test_sync_timeout_raises_not_implemented():
    with pytest.raises(NotImplementedError, match="timeout_ms is not supported for synchronous decorators"):
        @smooth_api(SmoothConfig(
            timeout_ms=100,
            backoff=BackoffConfig(max_retries=1, base_delay=0.01)
        ))
        def fetch_data_sync():
            return "success"
