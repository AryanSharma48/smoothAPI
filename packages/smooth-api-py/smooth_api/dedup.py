"""
Request deduplication for async-decorated functions.

When multiple coroutines call the same decorated function concurrently with
arguments that produce the same deduplication key, only the *first* coroutine
executes the underlying logic.  All subsequent callers receive an ``asyncio``
Future that resolves (or rejects) with exactly the same result.

The in-flight map is cleared for a key as soon as its Future settles, so the
next call *after* settlement triggers a brand-new execution.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable, Coroutine, Optional


def _default_key_fn(*args: Any, **kwargs: Any) -> str:
    """
    Default deduplication key: joins positional args with ':'.

    For a typical ``get_user(user_id)`` call this produces ``"42"``;
    for ``fetch_page(locale, page)`` it produces ``"en:2"``.
    """
    parts = [str(a) for a in args]
    parts += [f"{k}={v}" for k, v in sorted(kwargs.items())]
    return ":".join(parts)


class RequestDeduplicator:
    """
    Coalesces concurrent identical calls into a single execution.

    Parameters
    ----------
    key_fn:
        Optional function that derives a cache key from the call arguments.
        Must accept the same positional and keyword arguments as the wrapped
        coroutine function.  Return ``None`` to opt a specific call out of
        deduplication.  Defaults to :func:`_default_key_fn`.
    """

    def __init__(self, key_fn: Optional[Callable[..., Optional[str]]] = None) -> None:
        self._key_fn: Callable[..., Optional[str]] = key_fn or _default_key_fn
        # Maps deduplication key → asyncio.Future that wraps the in-flight coroutine.
        self._inflight: dict[str, asyncio.Future[Any]] = {}

    async def execute(
        self,
        thunk: Callable[[], Coroutine[Any, Any, Any]],
        call_args: tuple[Any, ...],
        call_kwargs: dict[str, Any],
    ) -> Any:
        """
        Execute *thunk* or return the result of an already-running call.

        Parameters
        ----------
        thunk:
            A **zero-argument** async callable (closure) containing the actual
            execution logic.  It already captures the original call arguments
            via closure, so we do **not** pass them through again.
        call_args:
            The original positional arguments — used **only** for key derivation.
        call_kwargs:
            The original keyword arguments — used **only** for key derivation.

        Returns
        -------
        Any
            The awaited result of *thunk* (shared across all concurrent
            callers with the same key).
        """
        key = self._key_fn(*call_args, **call_kwargs)

        # None key → bypass deduplication entirely for this call.
        if key is None:
            return await thunk()

        # Use get_running_loop() — get_event_loop() is deprecated when a loop
        # is already running (Python 3.10+) and emits DeprecationWarnings.
        loop = asyncio.get_running_loop()

        # asyncio.Future instances are bound to a specific event loop. Scope the
        # inflight key by loop id so calls from different loops don't try to
        # await a Future created in another loop.
        inflight_key = f"{id(loop)}:{key}"

        if inflight_key in self._inflight:
            # Another coroutine is already executing this call — share its Future.
            return await self._inflight[inflight_key]

        future: asyncio.Future[Any] = loop.create_future()
        self._inflight[inflight_key] = future

        try:
            result = await thunk()
            future.set_result(result)
            return result
        except BaseException as exc:
            # Catch BaseException (not just Exception) so that
            # asyncio.CancelledError — which is a BaseException in Python 3.8+
            # — also resolves the shared Future.  Without this, a cancelled
            # execution would leave the Future unresolved and any concurrent
            # waiters would hang forever.
            if not future.done():
                future.set_exception(exc)
            raise
        finally:
            # Always clean up so the next call (after settlement) runs fresh.
            self._inflight.pop(inflight_key, None)

    @property
    def inflight_count(self) -> int:
        """Number of currently in-flight deduplicated calls. Useful for tests."""
        return len(self._inflight)
