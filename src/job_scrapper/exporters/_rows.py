"""Shared bounded PostgreSQL row stream for dataset exports."""

from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Row

from job_scrapper.storage.postgres.models import JobModel
from job_scrapper.storage.postgres.session import DatabaseSessionManager
from job_scrapper.storage.postgres.job_filters import JobFilters, job_predicates


async def iter_job_batches(
    session_manager: DatabaseSessionManager, max_days: int | None, limit: int | None, filters: JobFilters | None = None
) -> AsyncIterator[list[Row[Any]]]:
    if max_days is not None and max_days < 1:
        raise ValueError("max_days must be positive")
    if limit is not None and limit < 0:
        raise ValueError("limit must be nonnegative")
    now = datetime.now(timezone.utc)
    stmt = select(
        JobModel.id, JobModel.source, JobModel.source_job_id, JobModel.source_url, JobModel.title,
        JobModel.company_name, JobModel.description_text, JobModel.posted_at,
        JobModel.scraped_at, JobModel.attributes,
    ).where(JobModel.posted_at <= now, *job_predicates(filters or JobFilters()))
    if max_days is not None:
        stmt = stmt.where(JobModel.posted_at >= now - timedelta(days=max_days))
    stmt = stmt.order_by(JobModel.posted_at.desc(), JobModel.id)
    if limit is not None:
        stmt = stmt.limit(limit)

    async with session_manager.session() as session:
        result = await session.stream(stmt)
        try:
            async for batch in result.partitions(500):
                yield batch
        finally:
            await result.close()


def record_from_row(row: Row[Any]) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "source": row.source,
        "source_job_id": row.source_job_id,
        "source_url": row.source_url,
        "title": row.title,
        "company_name": row.company_name,
        "description_text": row.description_text,
        "posted_at": row.posted_at.isoformat(),
        "scraped_at": row.scraped_at.isoformat(),
        "labels": row.attributes,
    }
