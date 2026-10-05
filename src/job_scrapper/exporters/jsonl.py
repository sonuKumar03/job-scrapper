"""ML Dataset Exporter to JSONL and Parquet formats."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any
from sqlalchemy import select
from job_scrapper.storage.postgres.models import JobModel
from job_scrapper.storage.postgres.session import DatabaseSessionManager


async def export_jobs_to_jsonl(
    session_manager: DatabaseSessionManager,
    output_path: str | Path,
    max_days: int | None = 7,
    limit: int | None = None,
) -> int:
    """Stream jobs from PostgreSQL into a JSONL dataset file formatted for ML classification."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    stmt = select(JobModel)
    if max_days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)
        stmt = stmt.where(JobModel.posted_at >= cutoff)

    stmt = stmt.order_by(JobModel.posted_at.desc())
    if limit:
        stmt = stmt.limit(limit)

    count = 0
    async with session_manager.session() as session:
        result = await session.stream(stmt)
        with open(path, "w", encoding="utf-8") as f:
            async for row in result.scalars():
                job: JobModel = row
                record = {
                    "id": str(job.id),
                    "source": job.source,
                    "source_url": job.source_url,
                    "title": job.title,
                    "company_name": job.company_name,
                    "description_text": job.description_text,
                    "posted_at": job.posted_at.isoformat(),
                    "scraped_at": job.scraped_at.isoformat(),
                    "labels": job.attributes,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1

    return count
