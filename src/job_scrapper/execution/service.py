"""Application facade and transactional outbox dispatcher."""

import asyncio
import logging
from uuid import UUID

from job_scrapper.execution.contracts import RunCapacity, RunConflict, RunSnapshot, RunStore, StartScrapeCommand, TaskTransport
from job_scrapper.execution.worker import WorkerPool

logger = logging.getLogger(__name__)


class ExecutionService:
    def __init__(self, store: RunStore, transport: TaskTransport, capacity: RunCapacity,
                 worker: WorkerPool | None = None, *, stop_pending_on_close: bool = True):
        self.store, self.transport, self.capacity, self.worker = store, transport, capacity, worker
        self._closed = False
        self._dispatcher: asyncio.Task | None = None
        self._supervisor: asyncio.Task | None = None
        self._failed = False
        self._stop_pending_on_close = stop_pending_on_close

    def start(self) -> None:
        if self.worker:
            self.worker.start()
        self._dispatcher = asyncio.create_task(self.dispatch())
        if self.worker:
            self._supervisor = asyncio.create_task(self.supervise())

    async def supervise(self) -> None:
        done, _ = await asyncio.wait(self.worker.tasks, return_when=asyncio.FIRST_COMPLETED)
        if self._closed:
            return
        self._failed = True
        for task in done:
            if not task.cancelled() and task.exception():
                logger.error('Execution host stopped: %s', type(task.exception()).__name__)
        await self.worker.abort()

    async def dispatch(self) -> None:
        while not self._closed and not self._failed:
            try:
                await self.store.dispatch_pending(self.transport.publish, self.capacity.queued)
            except Exception as error:
                logger.warning('Task dispatch deferred: %s', type(error).__name__)
            await asyncio.sleep(0.5)

    async def submit(self, command: StartScrapeCommand) -> RunSnapshot:
        self.check_health()
        return await self.store.create(command)

    def check_health(self) -> None:
        if self._closed or self._failed:
            raise RunConflict('Execution host unavailable. Restart the application before submitting work.')

    async def request_stop(self, run_id: UUID | None = None) -> RunSnapshot | None:
        return await self.store.request_stop(run_id)

    async def request_source_stop(self, run_id: UUID, source: str) -> RunSnapshot | None:
        return await self.store.request_source_stop(run_id, source)

    async def get(self, run_id: UUID) -> RunSnapshot | None:
        return await self.store.get(run_id)

    async def list_page(self, *, offset: int, limit: int) -> tuple[int, list[RunSnapshot]]:
        return await self.store.list_page(offset=offset, limit=limit)

    async def list_active(self) -> list[RunSnapshot]:
        return await self.store.list_active()

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        for task in (self._dispatcher, self._supervisor):
            if task:
                task.cancel()
        await asyncio.gather(*(t for t in (self._dispatcher, self._supervisor) if t), return_exceptions=True)
        if self.worker:
            try:
                if not self._failed:
                    for run in await self.store.list_active():
                        if self._stop_pending_on_close or run.status != 'queued':
                            await self.store.request_stop(run.id)
            finally:
                if self._failed:
                    await self.worker.abort()
                else:
                    await self.worker.aclose()
        await self.transport.aclose()
