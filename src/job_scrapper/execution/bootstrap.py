"""Composition root: the only place that chooses execution adapters."""

import asyncio
import logging
from contextlib import AsyncExitStack, asynccontextmanager
from functools import partial

from sqlalchemy import text

from job_scrapper.config import get_settings
from job_scrapper.companies.bootstrap import initialize_company_catalog
from job_scrapper.execution.contracts import RunCapacity, RunConflict, RunControl
from job_scrapper.execution.memory import MemoryTaskTransport
from job_scrapper.execution.service import ExecutionService
from job_scrapper.execution.worker import WorkerPool
from job_scrapper.runner import run_scrape
from job_scrapper.storage.postgres.runs import PostgresRunStore, host_ownership
from job_scrapper.storage.postgres.companies import PostgresCompanyTargetRepository
from job_scrapper.storage.postgres.session import DatabaseSessionManager
from job_scrapper.storage.postgres.sink import PostgresJobSink
from job_scrapper.utils.http_client import ResilientHttpClient


logger = logging.getLogger(__name__)


@asynccontextmanager
async def execution_runtime(manager: DatabaseSessionManager, *, worker_host: bool = False):
    settings = get_settings()
    capacity = RunCapacity(active=settings.scrape_max_active_runs, queued=settings.scrape_max_queued_runs)
    store = PostgresRunStore(manager, capacity, settings.scrape_executor)
    async with AsyncExitStack() as stack:
        if settings.scrape_executor == 'memory' and worker_host:
            raise ValueError('The worker command requires SCRAPE_EXECUTOR=broker.')
        await initialize_company_catalog(manager)
        embedded = settings.scrape_executor == 'memory'
        ownership = None
        if embedded or worker_host:
            try:
                ownership = await stack.enter_async_context(host_ownership(manager))
            except RunConflict:
                if worker_host:
                    raise
                logger.warning('Another host holds the execution lock; starting in API-only mode')
                embedded = False
            else:
                await store.recover_unfinished(requeue=not embedded)
        if embedded or ownership is None:
            transport = MemoryTaskTransport(capacity.queued)
        else:
            try:
                from job_scrapper.execution.redis import RedisTaskTransport
            except ImportError:
                raise ValueError('Broker mode requires: uv sync --extra broker') from None
            transport = RedisTaskTransport(settings.scrape_broker_url, settings.scrape_broker_stream)
        stack.push_async_callback(transport.aclose)
        worker = None
        if ownership is not None:
            if not embedded:
                await transport.prepare_consumer()
            client = ResilientHttpClient()
            stack.push_async_callback(client.close)
            pipeline = partial(run_scrape, company_repository=PostgresCompanyTargetRepository(manager),
                               source_timeout_seconds=settings.source_timeout_seconds,
                               source_timeouts=settings.source_timeouts)
            worker = WorkerPool(store, transport, pipeline, PostgresJobSink(manager), client, capacity.active)
        service: RunControl = ExecutionService(store, transport, capacity, worker, stop_pending_on_close=embedded)
        service.start()
        stack.push_async_callback(service.aclose)

        async def watch_owner():
            try:
                while True:
                    await asyncio.sleep(0.5)
                    if ownership.invalidated:
                        raise RuntimeError('Worker ownership lost.')
                    await ownership.execute(text('SELECT 1'))
                    await ownership.commit()
            except Exception:
                store.ownership_lost.set()
                service._failed = True

        monitor = asyncio.create_task(watch_owner()) if ownership is not None else None
        try:
            yield service
        finally:
            if monitor:
                monitor.cancel()
                await asyncio.gather(monitor, return_exceptions=True)


async def stop_run(manager: DatabaseSessionManager, run_id=None):
    settings = get_settings()
    store = PostgresRunStore(manager, RunCapacity(active=settings.scrape_max_active_runs,
                                                queued=settings.scrape_max_queued_runs), settings.scrape_executor)
    return await store.request_stop(run_id)
