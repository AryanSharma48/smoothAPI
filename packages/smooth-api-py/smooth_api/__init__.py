from __future__ import annotations

import asyncio
import functools
from urllib.parse import urlparse

from .config import ResilientConfig
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


def _get_status_code(err: Exception) -> int | None:
    if RequestsHTTPError and isinstance(err, RequestsHTTPError):
        return err.response.status_code
    if HttpxHTTPStatusError and isinstance(err, HttpxHTTPStatusError):
        return err.response.status_code
    return None


def resilient_api(config: ResilientConfig):
    def decorator(fn):
        # One breaker per decorated function, shared across all calls to fn.
        breaker = CircuitBreakerState(config.circuit_breaker)

        # fn.__qualname__ is the circuit key. Each decorated function gets its
        # own domain entry in the breaker map, isolated from all others.
        domain = fn.__qualname__

        if asyncio.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def wrapper(*args, **kwargs):
                # Runtime fallback overrides the config-level fallback.
                fallback = kwargs.pop('fallback', config.fallback)

                if not breaker.can_request(domain):
                    if fallback is not None:
                        return fallback
                    raise RuntimeError(f'Circuit breaker is OPEN for: {domain}')

                last_err: Exception | None = None

                for attempt in range(config.backoff.max_retries + 1):
                    try:
                        result = await fn(*args, **kwargs)
                        breaker.record_success(domain)
                        return result
                    except Exception as err:
                        status = _get_status_code(err)
                        # Non-retryable HTTP errors (e.g. 400, 401, 404) bubble up immediately.
                        if status is not None and status not in config.retry_on:
                            raise
                        breaker.record_failure(domain)
                        last_err = err
                        if attempt < config.backoff.max_retries:
                            await asyncio.sleep(calculate_backoff(attempt, config.backoff))

                raise last_err  # type: ignore[misc]

            return wrapper

        else:
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
                            raise
                        breaker.record_failure(domain)
                        last_err = err
                        if attempt < config.backoff.max_retries:
                            sleep_backoff(calculate_backoff(attempt, config.backoff))

                raise last_err  # type: ignore[misc]

            return wrapper

    return decorator


__all__ = ['resilient_api', 'ResilientConfig']