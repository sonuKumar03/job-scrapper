"""Run-scoped cooperative cancellation shared by execution and adapters."""

import asyncio
from contextvars import ContextVar

# Task-local because the worker shares one client across concurrent runs.
request_stop_event: ContextVar[asyncio.Event | None] = ContextVar('request_stop_event', default=None)


class RequestStopped(RuntimeError):
    """A queued request was stopped before reaching the network."""


async def wait_before_request(delay: float) -> None:
    stop = request_stop_event.get()
    if stop is not None and stop.is_set():
        raise RequestStopped()
    if delay <= 0:
        return
    if stop is None:
        await asyncio.sleep(delay)
        return
    try:
        await asyncio.wait_for(stop.wait(), timeout=delay)
    except TimeoutError:
        if not stop.is_set():
            return
    raise RequestStopped()
