"""Bounded process-local task delivery using the standard asyncio queue."""

import asyncio
from collections.abc import AsyncIterator

from job_scrapper.execution.contracts import ScrapeTask


class MemoryDelivery:
    def __init__(self, task: ScrapeTask, queue: asyncio.Queue[ScrapeTask]):
        self.task, self._queue, self._settled = task, queue, False

    async def ack(self) -> None:
        if not self._settled:
            self._queue.task_done()
            self._settled = True

    async def reject(self, *, requeue: bool) -> None:
        if self._settled:
            return
        if requeue:
            self._queue.put_nowait(self.task)
        await self.ack()


class MemoryTaskTransport:
    def __init__(self, capacity: int):
        self._queue: asyncio.Queue[ScrapeTask] = asyncio.Queue(maxsize=capacity)
        self._closed = False

    async def publish(self, task: ScrapeTask) -> None:
        if self._closed:
            raise RuntimeError('Task transport is closed.')
        self._queue.put_nowait(task)

    async def deliveries(self) -> AsyncIterator[MemoryDelivery]:
        while not self._closed:
            yield MemoryDelivery(await self._queue.get(), self._queue)

    async def aclose(self) -> None:
        self._closed = True
