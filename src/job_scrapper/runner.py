"""Shared scraping pipeline; persistence and networking arrive through ports."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from copy import deepcopy
from typing import Any
from job_scrapper.companies.contracts import ATS_PROVIDERS, CompanyCatalogUnavailable, CompanyTargetRepository

from job_scrapper.connectors.base import BaseConnector
from job_scrapper.connectors.registry import get_connector
from job_scrapper.execution.contracts import HttpClient, OwnershipLost, RunClaim, RunResult, RunStore, SourceUnavailable
from job_scrapper.storage.base import JobSink, StorageUnavailable
from job_scrapper.execution.cancellation import request_stop_event


async def run_scrape(
    claim: RunClaim, store: RunStore, sink: JobSink, client: HttpClient,
    source_limit: asyncio.Semaphore, stop_event: asyncio.Event,
    *, company_repository: CompanyTargetRepository,
    source_timeout_seconds: float = 900,
    source_timeouts: dict[str, int] | None = None,
) -> RunResult:
    results = {source: {'status': 'pending'} for source in claim.command.sources}
    state_lock = asyncio.Lock()
    source_stops = {source: asyncio.Event() for source in claim.command.sources}
    stopped_sources: set[str] = set()

    async def persist() -> None:
        await store.save_progress(claim, deepcopy(results))

    async def read_stop_requests() -> None:
        stop_run, sources = await store.stop_requests(claim)
        if stop_run:
            stop_event.set()
        stopped_sources.update(sources)
        for source, event in source_stops.items():
            if stop_event.is_set() or source in stopped_sources:
                event.set()

    async def watch_stop() -> None:
        while True:
            await read_stop_requests()
            await asyncio.sleep(0.5)

    @asynccontextmanager
    async def source_slot(source: str) -> AsyncIterator[bool]:
        acquire = asyncio.create_task(source_limit.acquire())
        stopped = asyncio.create_task(source_stops[source].wait())
        try:
            await asyncio.wait((acquire, stopped), return_when=asyncio.FIRST_COMPLETED)
            yield not source_stops[source].is_set()
        finally:
            acquire.cancel()
            stopped.cancel()
            await asyncio.gather(acquire, stopped, return_exceptions=True)
            if not acquire.cancelled() and acquire.result():
                source_limit.release()

    async def scrape_one(source: str) -> None:
        async with source_slot(source) as acquired:
            if not acquired or stop_event.is_set() or source in stopped_sources:
                async with state_lock:
                    results[source] = {**BaseConnector.new_stats(), 'status': 'stopped'}
                    await persist()
                return
            connector = None
            source_stop = source_stops[source]
            timeout_seconds = (source_timeouts or {}).get(source, source_timeout_seconds)
            timed_out = False

            async def watch_source() -> None:
                nonlocal timed_out
                try:
                    await asyncio.wait_for(source_stop.wait(), timeout=timeout_seconds)
                except TimeoutError:
                    timed_out = True
                source_stop.set()

            source_stats: dict[int, dict[str, Any]] = {}

            async def report_progress(stats: dict[str, Any]) -> None:
                # Each company has its own cumulative stats; retain identities across batches.
                async with state_lock:
                    source_stats[id(stats)] = stats
                    row = BaseConnector.new_stats()
                    for part in source_stats.values():
                        for key in ('found', 'inserted', 'skipped'):
                            row[key] += part[key]
                        row['errors'].extend(part['errors'])
                        row['truncated'] |= part['truncated']
                        if 'coverage' in part:
                            row['coverage'] = deepcopy(part['coverage'])
                        if 'warnings' in part:
                            row.setdefault('warnings', []).extend(part['warnings'])
                    results[source] = {**row, 'status': 'running'}
                    try:
                        await persist()
                    except OwnershipLost:
                        raise
                    except Exception as error:
                        raise StorageUnavailable(type(error).__name__) from error

            async with state_lock:
                results[source] = {**BaseConnector.new_stats(), 'status': 'pending'}
                await persist()
            stop_token = request_stop_event.set(source_stop)
            source_watcher = asyncio.create_task(watch_source())
            try:
                targets = await company_repository.list_enabled(source) if source in ATS_PROVIDERS else None
                if targets == ():
                    stats = {**BaseConnector.new_stats(), 'status': 'failed',
                             'errors': ['no enabled company targets'], 'truncated': True}
                    async with state_lock:
                        results[source] = stats
                        await persist()
                    return
                connector = get_connector(source, http_client=client, company_targets=targets)
                connector.stop_event = source_stop
                connector.on_progress = report_progress
                # Allow current requests and buffered saves to settle after the deadline.
                try:
                    async with asyncio.timeout(timeout_seconds + 60):
                        await connector.check_prerequisites()
                        if source_stop.is_set():
                            stats = BaseConnector.new_stats()
                        else:
                            async with state_lock:
                                results[source]['status'] = 'running'
                                await persist()
                            stats = await connector.scrape(sink=sink, max_days=claim.command.days)
                except TimeoutError:
                    timed_out = True
                    stats = deepcopy(results[source])
                manually_stopped = stop_event.is_set() or source in stopped_sources
                if timed_out and not manually_stopped:
                    stats['truncated'] = True
                    stats['timed_out'] = True
                    stats['errors'].append(f'Source deadline reached ({timeout_seconds:g} seconds); collection incomplete')
                stats = {**stats, 'status': 'stopped' if manually_stopped else
                         'failed' if stats['errors'] else 'partial' if stats['truncated'] else 'completed'}
            except (StorageUnavailable, CompanyCatalogUnavailable, OwnershipLost):
                raise
            except SourceUnavailable as error:
                stats = {**BaseConnector.new_stats(), 'status': 'failed',
                         'errors': [str(error)], 'truncated': True}
            except Exception as error:
                stats = {'status': 'failed', 'errors': [type(error).__name__], 'truncated': True}
            finally:
                source_watcher.cancel()
                await asyncio.gather(source_watcher, return_exceptions=True)
                request_stop_event.reset(stop_token)
                if connector is not None:
                    await connector.close()
            async with state_lock:
                results[source] = stats
                await persist()

    await read_stop_requests()
    watcher = asyncio.create_task(watch_stop())
    tasks = [asyncio.create_task(scrape_one(source)) for source in claim.command.sources]
    work = asyncio.gather(*tasks)
    try:
        done, _ = await asyncio.wait((work, watcher), return_when=asyncio.FIRST_COMPLETED)
        if watcher in done:
            await watcher
        await work
        await read_stop_requests()
        failures = sum(stats['status'] == 'failed' for stats in results.values())
        incomplete = any(stats['status'] in ('partial', 'stopped') for stats in results.values())
        all_stopped = all(stats['status'] == 'stopped' for stats in results.values())
        status = 'stopped' if stop_event.is_set() or all_stopped else 'completed' if not failures and not incomplete else (
            'failed' if failures == len(results) else 'partial'
        )
        return RunResult(status=status, results=results)
    finally:
        watcher.cancel()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(watcher, *tasks, return_exceptions=True)
        await asyncio.gather(work, return_exceptions=True)
