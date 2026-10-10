"""Shared scraping pipeline; persistence and networking arrive through ports."""

import asyncio
from copy import deepcopy
from typing import Any
from job_scrapper.companies.contracts import ATS_PROVIDERS, CompanyCatalogUnavailable, CompanyTargetRepository

from job_scrapper.connectors.base import BaseConnector
from job_scrapper.connectors.registry import get_connector
from job_scrapper.execution.contracts import HttpClient, OwnershipLost, RunClaim, RunResult, RunStore
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

    async def persist() -> None:
        await store.save_progress(claim, deepcopy(results))

    async def watch_stop() -> None:
        while True:
            if await store.stop_requested(claim):
                stop_event.set()
            await asyncio.sleep(0.5)

    async def scrape_one(source: str) -> None:
        async with source_limit:
            if stop_event.is_set():
                async with state_lock:
                    results[source] = {**BaseConnector.new_stats(), 'status': 'stopped'}
                    await persist()
                return
            connector = None
            source_stop = asyncio.Event()
            timeout_seconds = (source_timeouts or {}).get(source, source_timeout_seconds)
            timed_out = False

            async def watch_source() -> None:
                nonlocal timed_out
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=timeout_seconds)
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
                results[source] = {**BaseConnector.new_stats(), 'status': 'running'}
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
                    stats = await asyncio.wait_for(connector.scrape(sink=sink, max_days=claim.command.days),
                                                   timeout=timeout_seconds + 60)
                except TimeoutError:
                    timed_out = True
                    stats = deepcopy(results[source])
                if timed_out:
                    stats['truncated'] = True
                    stats['timed_out'] = True
                    stats['errors'].append(f'Source deadline reached ({timeout_seconds:g} seconds); collection incomplete')
                stats = {**stats, 'status': 'stopped' if stop_event.is_set() else
                         'failed' if stats['errors'] else 'partial' if stats['truncated'] else 'completed'}
            except (StorageUnavailable, CompanyCatalogUnavailable, OwnershipLost):
                raise
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

    watcher = asyncio.create_task(watch_stop())
    tasks = [asyncio.create_task(scrape_one(source)) for source in claim.command.sources]
    work = asyncio.gather(*tasks)
    try:
        done, _ = await asyncio.wait((work, watcher), return_when=asyncio.FIRST_COMPLETED)
        if watcher in done:
            await watcher
        await work
        if await store.stop_requested(claim):
            stop_event.set()
        failures = sum(stats['status'] == 'failed' for stats in results.values())
        incomplete = any(stats['status'] == 'partial' for stats in results.values())
        status = 'stopped' if stop_event.is_set() else 'completed' if not failures and not incomplete else (
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
