"""Common bounded worker pool; acknowledgement follows committed run state."""

import asyncio
from collections.abc import Awaitable, Callable
from uuid import UUID

from job_scrapper.execution.contracts import HttpClient, OwnershipLost, RunClaim, RunResult, RunStore, TaskTransport
from job_scrapper.storage.base import JobSink

Pipeline = Callable[[RunClaim, RunStore, JobSink, HttpClient, asyncio.Semaphore, asyncio.Event], Awaitable[RunResult]]


class WorkerPool:
    def __init__(self, store: RunStore, transport: TaskTransport, pipeline: Pipeline,
                 sink: JobSink, client: HttpClient, concurrency: int):
        self.store, self.transport, self.pipeline = store, transport, pipeline
        self.sink, self.client, self.concurrency = sink, client, concurrency
        self.source_limit = asyncio.Semaphore(3)
        self.stops: dict[UUID, asyncio.Event] = {}
        self.tasks: list[asyncio.Task] = []
        self._busy: set[asyncio.Task] = set()
        self._closing = False

    def start(self) -> None:
        self.tasks = [asyncio.create_task(self.consume()) for _ in range(self.concurrency)]

    async def consume(self) -> None:
        async for delivery in self.transport.deliveries():
            if self._closing:
                return
            async with self.store.claim(delivery.task) as claim:
                if claim is None:
                    await delivery.ack()
                    continue
                task = asyncio.current_task()
                self._busy.add(task)
                stop = self.stops[claim.run_id] = asyncio.Event()
                try:
                    try:
                        result = await self.pipeline(claim, self.store, self.sink, self.client, self.source_limit, stop)
                    except asyncio.CancelledError:
                        if self._closing:
                            current = await self.store.get(claim.run_id)
                            await self.store.finish(claim, RunResult(status='interrupted', results=current.results,
                                                                   error_message='Worker shutdown exceeded the grace period.'))
                        else:
                            await self.store.schedule_retry(claim, 'Execution channel interrupted.', 5 if claim.attempt == 1 else 30)
                        raise
                    except OwnershipLost:
                        raise
                    except Exception as error:
                        await self.store.schedule_retry(claim, type(error).__name__, 5 if claim.attempt == 1 else 30)
                    else:
                        await self.store.finish(claim, result)
                    await delivery.ack()
                finally:
                    self.stops.pop(claim.run_id, None)
                    self._busy.discard(task)
            if self._closing:
                return

    async def abort(self) -> None:
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def aclose(self) -> None:
        self._closing = True
        for stop in self.stops.values():
            stop.set()
        for task in self.tasks:
            if task not in self._busy:
                task.cancel()
        try:
            await asyncio.wait_for(asyncio.gather(*self.tasks, return_exceptions=True), timeout=60)
        except TimeoutError:
            await asyncio.gather(*self.tasks, return_exceptions=True)
