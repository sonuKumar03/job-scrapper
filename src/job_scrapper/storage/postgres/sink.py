"""PostgreSQL storage sink with 3-layer deduplication and sightings ledger."""

import uuid
from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from job_scrapper.domain.dedup import DeduplicationEngine
from job_scrapper.domain.models import JobPosting
from job_scrapper.pipeline.dedup_engine import StandardDeduplicationEngine
from job_scrapper.storage.postgres.models import JobModel, JobSightingModel
from job_scrapper.storage.postgres.session import DatabaseSessionManager


class PostgresJobSink:
    """PostgreSQL implementation of JobSink with 3-layer deduplication and attribute enrichment."""

    def __init__(
        self,
        session_manager: DatabaseSessionManager,
        dedup_engine: DeduplicationEngine | None = None,
    ) -> None:
        self.session_manager = session_manager
        self.dedup_engine = dedup_engine or StandardDeduplicationEngine()

    async def contains(self, source: str, source_job_id: str) -> bool:
        """Check if job exists in jobs or job_sightings."""
        async with self.session_manager.session() as session:
            stmt = (
                select(JobSightingModel.id)
                .where(
                    JobSightingModel.source == source,
                    JobSightingModel.source_job_id == source_job_id,
                )
                .limit(1)
            )
            result = await session.execute(stmt)
            if result.scalar_one_or_none() is not None:
                return True

            # Also fallback check in jobs table
            stmt_job = (
                select(JobModel.id)
                .where(
                    JobModel.source == source,
                    JobModel.source_job_id == source_job_id,
                )
                .limit(1)
            )
            result_job = await session.execute(stmt_job)
            return result_job.scalar_one_or_none() is not None

    async def save_batch(self, jobs: list[JobPosting]) -> int:
        if not jobs:
            return 0

        # Pre-compute signatures and simhashes
        prepared: list[tuple[JobPosting, str, int]] = []
        content_hashes = []
        canonical_signatures = []

        for job in jobs:
            sig = self.dedup_engine.compute_canonical_signature(job)
            sim = self.dedup_engine.compute_simhash(job.description_text)
            prepared.append((job, sig, sim))
            content_hashes.append(job.content_hash)
            canonical_signatures.append(sig)

        new_jobs_inserted = 0

        async with self.session_manager.session() as session:
            # 1. Lookup existing canonical jobs matching content_hash or canonical_signature
            stmt = select(JobModel).where(
                or_(
                    JobModel.content_hash.in_(content_hashes),
                    JobModel.canonical_signature.in_(canonical_signatures),
                )
            )
            existing_results = await session.execute(stmt)
            existing_jobs = existing_results.scalars().all()

            # Map existing by content_hash and canonical_signature
            existing_by_hash: dict[str, JobModel] = {j.content_hash: j for j in existing_jobs}
            existing_by_sig: dict[str, JobModel] = {
                j.canonical_signature: j for j in existing_jobs if j.canonical_signature
            }

            records_to_insert = []
            sightings_to_insert = []

            for job, sig, sim in prepared:
                # Find matching canonical job (Layer 1 & Layer 2)
                matched_job = existing_by_hash.get(job.content_hash) or existing_by_sig.get(sig)

                # Check SimHash near-duplicate if not matched yet
                if not matched_job and sim != 0:
                    for cand in existing_jobs:
                        if cand.simhash and self.dedup_engine.are_near_duplicates(sim, cand.simhash):
                            matched_job = cand
                            break

                if matched_job:
                    # Layer 3: Record sighting and enrich attributes
                    sightings_to_insert.append({
                        "id": uuid.uuid4(),
                        "job_id": matched_job.id,
                        "source": job.source,
                        "source_job_id": job.source_job_id,
                        "source_url": job.source_url,
                        "seen_at": job.scraped_at,
                    })

                    # Attribute enrichment
                    merged_attrs, changed = self.dedup_engine.enrich_attributes(
                        matched_job.attributes, job.attributes
                    )
                    if changed:
                        matched_job.attributes = merged_attrs
                        await session.execute(
                            update(JobModel)
                            .where(JobModel.id == matched_job.id)
                            .values(attributes=merged_attrs)
                        )
                else:
                    # Brand new job
                    new_id = uuid.uuid4()
                    records_to_insert.append({
                        "id": new_id,
                        "source": job.source,
                        "source_job_id": job.source_job_id,
                        "source_url": job.source_url,
                        "title": job.title,
                        "company_name": job.company_name,
                        "description_text": job.description_text,
                        "posted_at": job.posted_at,
                        "scraped_at": job.scraped_at,
                        "content_hash": job.content_hash,
                        "canonical_signature": sig,
                        "simhash": sim,
                        "attributes": job.attributes,
                    })
                    sightings_to_insert.append({
                        "id": uuid.uuid4(),
                        "job_id": new_id,
                        "source": job.source,
                        "source_job_id": job.source_job_id,
                        "source_url": job.source_url,
                        "seen_at": job.scraped_at,
                    })

            # Bulk insert new canonical jobs
            if records_to_insert:
                stmt_insert = insert(JobModel).values(records_to_insert)
                stmt_insert = stmt_insert.on_conflict_do_nothing(
                    index_elements=["content_hash"]
                ).returning(JobModel.id)
                res = await session.execute(stmt_insert)
                inserted_ids = res.scalars().all()
                new_jobs_inserted = len(inserted_ids)

            # Bulk insert sightings
            if sightings_to_insert:
                stmt_sightings = insert(JobSightingModel).values(sightings_to_insert)
                stmt_sightings = stmt_sightings.on_conflict_do_nothing(
                    constraint="uq_sightings_source_job_id"
                )
                await session.execute(stmt_sightings)

            await session.commit()

        return new_jobs_inserted

    async def count(self) -> int:
        async with self.session_manager.session() as session:
            stmt = select(func.count(JobModel.id))
            result = await session.execute(stmt)
            return result.scalar() or 0

    async def count_sightings(self) -> int:
        async with self.session_manager.session() as session:
            stmt = select(func.count(JobSightingModel.id))
            result = await session.execute(stmt)
            return result.scalar() or 0
