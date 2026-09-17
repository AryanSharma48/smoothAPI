from __future__ import annotations

import asyncio
import functools
import inspect
from typing import Any

from .config import (
    CircuitState,
    CircuitStateChangeEvent,
    DeduplicationConfig,
    RetryContext,
    SmoothConfig,
)
from .dedup import RequestDeduplicator
from .state import CircuitBreakerState
from .utils import calculate_backoff, sleep_backoff

try:
    from requests.exceptions import HTTPError as RequestsHTTPError
except ImportError:
    RequestsHTTPError = None  # type: ignore[assignment,misc]

try:
    from httpx import HTTPStatusError as HttpxHTTPStatusError
except ImportError:
    HttpxHTTPStatusError = None  # type: ignore[assignment,misc]


def _safe_invoke(fn: Any, arg: Any) -> None:
    if fn is None:
        return
    try:
        res = fn(arg)
        if inspect.iscoroutine(res):
            try:
                loop = asyncio.get_running_loop()
                task = loop.create_task(res)
                def _handle_task_done(t: asyncio.Task) -> None:
                    if not t.cancelled() and t.exception():
                        import sys
                        sys.stderr.write(f"[smoothAPI] Error in async lifecycle hook: {t.exception()}\n")
                task.add_done_callback(_handle_task_done)
            except RuntimeError:
                asyncio.run(res)
    except Exception as ex:
        import sys
        sys.stderr.write(f"[smoothAPI] Error in lifecycle hook: {ex}\n")


def _extract_url(args: tuple, kwargs: dict) -> str:
    if "url" in kwargs and isinstance(kwargs["url"], str):
        return kwargs["url"]
    for arg in args:
        if isinstance(arg, str) and (arg.startswith(("http://", "https://")) or "/" in arg):
            return arg
    if args and isinstance(args[0], str):
        return args[0]
    return ""



def _get_status_code(err: Exception) -> int | None:
    if RequestsHTTPError is not None and isinstance(err, RequestsHTTPError):
        if err.response is not None:
            return err.response.status_code
    if HttpxHTTPStatusError is not None and isinstance(err, HttpxHTTPStatusError):
        if err.response is not None:
            return err.response.status_code
    return None


def _get_retry_after_delay(err: Exception) -> float | None:
    if hasattr(err, "response") and err.response is not None:
        if hasattr(err.response, "headers"):
            retry_after = err.response.headers.get("Retry-After")
            if retry_after is not None:
                try:
                    delay = float(retry_after)
                    if delay > 0:
                        return delay
                except ValueError:
                    pass
    return None


class MockResponse:
    def __init__(self, status_code: int, content: dict, reason: str = ""):
        self.status_code = status_code
        self._content = content
        self.reason = reason
        self.reason_phrase = reason

    def json(self) -> dict:
        return self._content

    @property
    def text(self) -> str:
        import json
        return json.dumps(self._content)

    @property
    def ok(self) -> bool:
        return self.status_code < 400

    def raise_for_status(self) -> None:
        pass


def smooth_api(config: SmoothConfig):
    def decorator(fn):
        # One breaker per decorated function, shared across all calls to fn.
        breaker = CircuitBreakerState(config.circuit_breaker, config.on_circuit_state_change)

        # fn.__qualname__ is the circuit key. Each decorated function gets its
        # own domain entry in the breaker map, isolated from all others.
        domain = fn.__qualname__

        # One deduplicator per decorated function (None when feature is off).
        deduplicator = (
            RequestDeduplicator(config.deduplication.key_fn)
            if config.deduplication is not None
            else None
        )

        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def wrapper(*args, **kwargs):
                # Runtime fallback overrides the config-level fallback.
                fallback = kwargs.pop('fallback', config.fallback)

                if not breaker.can_request(domain):
                    if fallback is not None:
                        return fallback
                    raise RuntimeError(f'Circuit breaker is OPEN for: {domain}')

                # Inner coroutine that contains the retry+breaker logic.
                # Extracted so the deduplicator can decide whether to run it
                # or attach to an already-running Future.
                async def _execute():
                    last_err: Exception | None = None

                    for attempt in range(config.backoff.max_retries + 1):
                        try:
                            if config.timeout_ms is not None:
                                result = await asyncio.wait_for(fn(*args, **kwargs), timeout=config.timeout_ms / 1000.0)
                            else:
                                result = await fn(*args, **kwargs)
                            breaker.record_success(domain)
                            return result
                        except asyncio.CancelledError:
                            # CancelledError is a BaseException (Python 3.8+) and
                            # escapes `except Exception`.  We still need to record
                            # the failure so sustained cancellation (e.g. client
                            # timeouts) is counted toward tripping the circuit,
                            # then re-raise so the cancellation propagates normally.
                            breaker.record_failure(domain)
                            raise
                        except Exception as err:
                            status = _get_status_code(err)
                            # Non-retryable HTTP errors (e.g. 400, 401, 404) bubble up immediately.
                            if status is not None and status not in config.retry_on:
                                if config.fallback_on_non_retryable:
                                    import sys
                                    reason = getattr(err.response, 'reason', getattr(err.response, 'reason_phrase', ''))
                                    message = f"Non-retryable HTTP error: {status} {reason}".strip()
                                    if config.on_non_retryable_error:
                                        config.on_non_retryable_error(status, message)
                                    else:
                                        sys.stderr.write(f"{message}\n")
                                    
                                    breaker.record_success(domain)
                                    if fallback is not None:
                                        return fallback
                                    return MockResponse(
                                        status_code=status,
                                        content={"error": True, "status": status, "message": message},
                                        reason=reason
                                    )
                                raise
                            breaker.record_failure(domain)
                            last_err = err
                            if attempt < config.backoff.max_retries:
                                delay = calculate_backoff(attempt, config.backoff)
                                if status == 429:
                                    retry_after_delay = _get_retry_after_delay(err)
                                    if retry_after_delay is not None:
                                        delay = retry_after_delay
                                if config.on_retry:
                                    ctx = RetryContext(
                                        attempt=attempt + 1,
                                        max_retries=config.backoff.max_retries,
                                        delay_ms=delay * 1000.0,
                                        status=status,
                                        error=err,
                                        url=_extract_url(args, kwargs),
                                        domain=domain,
                                    )
                                    _safe_invoke(config.on_retry, ctx)
                                await asyncio.sleep(delay)
                                continue
                                
                            # If retries are exhausted and it's an HTTP error, return the response instead of raising
                            if status is not None and hasattr(err, 'response'):
                                return err.response

                    raise last_err  # type: ignore[misc]

                if deduplicator is not None:
                    return await deduplicator.execute(_execute, args, kwargs)

                return await _execute()

            return wrapper

        else:
            if deduplicator is not None:
                import warnings
                # Sync deduplication requires a thread-safe lock manager, which is currently unsupported
                warnings.warn("Synchronous deduplication is not supported. Deduplication will be ignored for this function.", UserWarning, stacklevel=2)
                
            if config.timeout_ms is not None:
                raise NotImplementedError("timeout_ms is not supported for synchronous decorators. Please use your HTTP client's native timeout support.")

            @functools.wraps(fn)
            def wrapper(*args, **kwargs):  # type: ignore[misc]
                fallback = kwargs.pop('fallback', config.fallback)

                if not breaker.can_request(domain):
                    if fallback is not None:
                        return fallback
                    raise RuntimeError(f'Circuit breaker is OPEN for: {domain}')

                last_err: Exception | None = None

                for attempt in range(config.backoff.max_retries + 1):
                    try:
                        result = fn(*args, **kwargs)
                        breaker.record_success(domain)
                        return result
                    except Exception as err:
                        status = _get_status_code(err)
                        if status is not None and status not in config.retry_on:
                            if config.fallback_on_non_retryable:
                                import sys
                                reason = getattr(err.response, 'reason', getattr(err.response, 'reason_phrase', ''))
                                message = f"Non-retryable HTTP error: {status} {reason}".strip()
                                if config.on_non_retryable_error:
                                    config.on_non_retryable_error(status, message)
                                else:
                                    sys.stderr.write(f"{message}\n")
                                
                                breaker.record_success(domain)
                                if fallback is not None:
                                    return fallback
                                return MockResponse(
                                    status_code=status,
                                    content={"error": True, "status": status, "message": message},
                                    reason=reason
                                )
                            raise
                        breaker.record_failure(domain)
                        last_err = err
                        if attempt < config.backoff.max_retries:
                            delay = calculate_backoff(attempt, config.backoff)
                            if status == 429:
                                retry_after_delay = _get_retry_after_delay(err)
                                if retry_after_delay is not None:
                                    delay = retry_after_delay
                            if config.on_retry:
                                ctx = RetryContext(
                                    attempt=attempt + 1,
                                    max_retries=config.backoff.max_retries,
                                    delay_ms=delay * 1000.0,
                                    status=status,
                                    error=err,
                                    url=_extract_url(args, kwargs),
                                    domain=domain,
                                )
                                _safe_invoke(config.on_retry, ctx)
                            sleep_backoff(delay)
                            continue
                            
                        if status is not None and hasattr(err, 'response'):
                            return err.response

                raise last_err  # type: ignore[misc]

            return wrapper

    return decorator


__all__ = [
    'smooth_api',
    'SmoothConfig',
    'DeduplicationConfig',
    'RetryContext',
    'CircuitStateChangeEvent',
    'CircuitState',
    'resilient_api',
    'ResilientConfig',
]

import warnings

def resilient_api(*args, **kwargs):
    warnings.warn("'resilient_api' is deprecated, use 'smooth_api' instead", DeprecationWarning, stacklevel=2)
    return smooth_api(*args, **kwargs)

class ResilientConfig(SmoothConfig):
    def __init__(self, *args, **kwargs):
        warnings.warn("'ResilientConfig' is deprecated, use 'SmoothConfig' instead", DeprecationWarning, stacklevel=2)
        super().__init__(*args, **kwargs)