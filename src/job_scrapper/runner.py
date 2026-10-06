"""Shared CLI/web execution, durable results, and exclusion with database reset."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text, update

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


async def reconcile_executions(manager: DatabaseSessionManager) -> None:
    """Only reconcile stale executions when no managed scraper is running."""
    try:
        async with scrape_lock(manager), manager.session() as session:
            await session.execute(update(ScrapeExecutionModel).where(
                ScrapeExecutionModel.status == "running"
            ).values(status="interrupted", finished_at=datetime.now(timezone.utc),
                     error_message="Execution process stopped before completion."))
            await session.commit()
    except ScrapeBusyError:
        pass


async def run_scrape(
    manager: DatabaseSessionManager, sources: list[str], days: int,
    on_update: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
) -> dict[str, Any]:
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
                ).values(results=deepcopy(row.results), status=row.status,
                         finished_at=row.finished_at, error_message=row.error_message))
                await session.commit()
            if on_update:
                await on_update(deepcopy(execution_snapshot(row)))

        client = ResilientHttpClient()
        sink = PostgresJobSink(manager)
        source_limit = asyncio.Semaphore(3)

        async def scrape_one(source: str) -> None:
            async with source_limit:
                connector = None
                async with state_lock:
                    row.results[source] = {"status": "running"}
                    await persist()
                try:
                    connector = get_connector(source, http_client=client)
                    stats = await connector.scrape(sink=sink, max_days=days)
                    stats = {**stats, "status": "failed" if stats["errors"] or stats["truncated"] else "completed"}
                except Exception as error:
                    stats = {"status": "failed", "errors": [type(error).__name__], "truncated": True}
                finally:
                    if connector is not None:
                        await connector.close()
                async with state_lock:
                    row.results[source] = stats
                    await persist()

        tasks: list[asyncio.Task[None]] = []
        try:
            await persist()  # The web caller receives an ID only after lock acquisition and commit.
            tasks = [asyncio.create_task(scrape_one(source)) for source in sources]
            await asyncio.gather(*tasks)
            failures = sum(result["status"] == "failed" for result in row.results.values())
            row.status = "completed" if not failures else "failed" if failures == len(sources) else "partial"
        except asyncio.CancelledError:
            row.status = "interrupted"
            row.error_message = "Execution was interrupted."
            raise
        except Exception as error:
            row.status = "failed"
            row.error_message = type(error).__name__
            raise
        finally:
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
