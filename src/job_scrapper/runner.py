"""Shared CLI/web execution, durable results, and exclusion with database reset."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import case, select, text, update

from job_scrapper.connectors.base import BaseConnector
from job_scrapper.connectors.registry import get_connector, list_connectors
from job_scrapper.storage.postgres.models import ScrapeExecutionModel
from job_scrapper.storage.postgres.session import DatabaseSessionManager
from job_scrapper.storage.postgres.sink import PostgresJobSink
from job_scrapper.utils.http_client import ResilientHttpClient

# Session-level lock shared by CLI, web, and reset; held on a dedicated connection.
SCRAPE_LOCK_KEY = 726384102


class ScrapeBusyError(Exception):
    """Another scrape or reset owns the execution lock."""


@asynccontextmanager
async def scrape_lock(manager: DatabaseSessionManager) -> AsyncIterator[None]:
    async with manager.engine.connect() as connection:
        try:
            acquired = await connection.scalar(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": SCRAPE_LOCK_KEY}
            )
            await connection.commit()
        except BaseException:
            # The server may have acquired the lock even if its response was cancelled.
            await connection.invalidate()
            raise
        if not acquired:
            raise ScrapeBusyError("A scrape or database reset is already running.")
        try:
            yield
        finally:
            try:
                await connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": SCRAPE_LOCK_KEY})
                await connection.commit()
            except BaseException:
                # Never return a session holding the lock to the connection pool.
                await connection.invalidate()
                raise


def execution_snapshot(row: ScrapeExecutionModel) -> dict[str, Any]:
    return {
        "id": str(row.id), "sources": row.sources, "days": row.days,
        "status": row.status, "started_at": row.started_at.isoformat(),
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "results": row.results, "error_message": row.error_message,
    }


async def request_scrape_stop(manager: DatabaseSessionManager, run_id: UUID | None = None) -> str | None:
    """Request a stop in the shared database so CLI and web can stop either owner."""
    statement = update(ScrapeExecutionModel).where(ScrapeExecutionModel.status.in_(["running", "stopping"]))
    if run_id is not None:
        statement = statement.where(ScrapeExecutionModel.id == run_id)
    async with manager.session() as session:
        result = await session.scalar(statement.values(status="stopping").returning(ScrapeExecutionModel.id))
        await session.commit()
    return str(result) if result is not None else None


async def reconcile_executions(manager: DatabaseSessionManager) -> None:
    """Only reconcile stale executions when no managed scraper is running."""
    try:
        async with scrape_lock(manager), manager.session() as session:
            await session.execute(update(ScrapeExecutionModel).where(
                ScrapeExecutionModel.status.in_(["running", "stopping"])
            ).values(status="interrupted", finished_at=datetime.now(timezone.utc),
                     error_message="Execution process stopped before completion."))
            await session.commit()
    except ScrapeBusyError:
        pass


async def run_scrape(
    manager: DatabaseSessionManager, sources: list[str], days: int,
    on_update: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    stop_event: asyncio.Event | None = None,
) -> dict[str, Any]:
    stop_event = stop_event if stop_event is not None else asyncio.Event()
    sources = list(dict.fromkeys(sources))
    if days < 1 or not sources or set(sources) - set(list_connectors()):
        raise ValueError("Select registered sources and a positive day window.")
    async with scrape_lock(manager):
        row = ScrapeExecutionModel(
            sources=sources, days=days, status="running",
            started_at=datetime.now(timezone.utc),
            results={source: {"status": "pending"} for source in sources},
        )
        async with manager.session() as session:
            session.add(row)
            await session.commit()
        state_lock = asyncio.Lock()

        async def persist() -> None:
            async with manager.session() as session:
                await session.execute(update(ScrapeExecutionModel).where(
                    ScrapeExecutionModel.id == row.id
                ).values(results=deepcopy(row.results), status=case(
                         (ScrapeExecutionModel.status == "stopping", "stopping"),
                         else_=row.status,
                     ) if row.status == "running" else row.status,
                         finished_at=row.finished_at, error_message=row.error_message))
                await session.commit()
            if on_update:
                await on_update(deepcopy(execution_snapshot(row)))

        client = ResilientHttpClient()
        sink = PostgresJobSink(manager)
        source_limit = asyncio.Semaphore(3)

        async def watch_stop() -> None:
            while True:
                async with manager.session() as session:
                    status = await session.scalar(select(ScrapeExecutionModel.status).where(ScrapeExecutionModel.id == row.id))
                if status == "stopping":
                    stop_event.set()
                if stop_event.is_set():
                    async with state_lock:
                        row.status = "stopping"
                        await persist()
                    return
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=1)
                except TimeoutError:
                    pass

        async def scrape_one(source: str) -> None:
            async with source_limit:
                if stop_event.is_set():
                    async with state_lock:
                        row.results[source] = {**BaseConnector.new_stats(), "status": "stopped"}
                        await persist()
                    return
                connector = None
                async with state_lock:
                    row.results[source] = {"status": "running"}
                    await persist()
                try:
                    connector = get_connector(source, http_client=client)
                    connector.stop_event = stop_event
                    stats = await connector.scrape(sink=sink, max_days=days)
                    stats = {**stats, "status": "stopped" if stop_event.is_set() else "failed" if stats["errors"] or stats["truncated"] else "completed"}
                except Exception as error:
                    stats = {"status": "failed", "errors": [type(error).__name__], "truncated": True}
                finally:
                    if connector is not None:
                        await connector.close()
                async with state_lock:
                    row.results[source] = stats
                    await persist()

        tasks: list[asyncio.Task[None]] = []
        stop_watcher: asyncio.Task[None] | None = None
        try:
            await persist()  # The web caller receives an ID only after lock acquisition and commit.
            stop_watcher = asyncio.create_task(watch_stop())
            tasks = [asyncio.create_task(scrape_one(source)) for source in sources]
            await asyncio.gather(*tasks)
            if stop_watcher.done():
                await stop_watcher  # Surface database failures in the control channel.
            async with manager.session() as session:
                status = await session.scalar(select(ScrapeExecutionModel.status).where(ScrapeExecutionModel.id == row.id))
            if status == "stopping":
                stop_event.set()
            failures = sum(result["status"] == "failed" for result in row.results.values())
            row.status = "stopped" if stop_event.is_set() else "completed" if not failures else "failed" if failures == len(sources) else "partial"
        except asyncio.CancelledError:
            row.status = "interrupted"
            row.error_message = "Execution was interrupted."
            raise
        except Exception as error:
            row.status = "failed"
            row.error_message = type(error).__name__
            raise
        finally:
            if stop_watcher is not None:
                stop_watcher.cancel()
                await asyncio.gather(stop_watcher, return_exceptions=True)
            if row.status in {"interrupted", "failed"}:
                for result in row.results.values():
                    if result["status"] in {"running", "pending"}:
                        result["status"] = row.status
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            try:
                await client.close()
            finally:
                row.finished_at = datetime.now(timezone.utc)
                await persist()
        return execution_snapshot(row)
