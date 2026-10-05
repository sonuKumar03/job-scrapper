"""PostgreSQL storage sink implementation using SQLAlchemy 2.0."""

import uuid
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from job_scrapper.domain.models import JobPosting
from job_scrapper.storage.postgres.models import JobModel
from job_scrapper.storage.postgres.session import DatabaseSessionManager


class PostgresJobSink:
    """PostgreSQL implementation of JobSink with atomic batch upserts."""

    def __init__(self, session_manager: DatabaseSessionManager) -> None:
        self.session_manager = session_manager

    async def contains(self, source: str, source_job_id: str) -> bool:
        async with self.session_manager.session() as session:
            stmt = (
                select(JobModel.id)
                .where(
                    JobModel.source == source,
                    JobModel.source_job_id == source_job_id,
                )
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None

    async def save_batch(self, jobs: list[JobPosting]) -> int:
        if not jobs:
            return 0

        # Build raw dict records
        records = []
        for job in jobs:
            records.append({
                "id": uuid.uuid4(),
                "source": job.source,
                "source_job_id": job.source_job_id,
                "source_url": job.source_url,
                "title": job.title,
                "company_name": job.company_name,
                "description_text": job.description_text,
                "posted_at": job.posted_at,
                "scraped_at": job.scraped_at,
                "content_hash": job.content_hash,
                "attributes": job.attributes,
            })

        stmt = insert(JobModel).values(records)
        # Skip duplicates matching content_hash
        stmt = stmt.on_conflict_do_nothing(index_elements=["content_hash"]).returning(JobModel.id)

        async with self.session_manager.session() as session:
            result = await session.execute(stmt)
            await session.commit()
            inserted_ids = result.scalars().all()
            return len(inserted_ids)

    async def count(self) -> int:
        async with self.session_manager.session() as session:
            stmt = select(func.count(JobModel.id))
            result = await session.execute(stmt)
            return result.scalar() or 0
