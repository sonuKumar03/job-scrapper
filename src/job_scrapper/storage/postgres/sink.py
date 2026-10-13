"""PostgreSQL storage sink with 3-layer deduplication and sightings ledger."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from hashlib import sha256
from sqlalchemy import func, select, text, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DisconnectionError, InterfaceError, OperationalError, TimeoutError
from sqlalchemy.ext.asyncio import AsyncSession
from job_scrapper.storage.base import StorageUnavailable
from job_scrapper.domain.models import JobPosting
from job_scrapper.pipeline.dedup_engine import StandardDeduplicationEngine
from job_scrapper.storage.postgres.models import JobModel, JobSightingModel
from job_scrapper.storage.postgres.session import DatabaseSessionManager


class PostgresJobSink:
    """PostgreSQL implementation of JobSink with 3-layer deduplication and attribute enrichment."""

    def __init__(
        self,
        session_manager: DatabaseSessionManager,
        dedup_engine: StandardDeduplicationEngine | None = None,
    ) -> None:
        self.session_manager = session_manager
        self.dedup_engine = dedup_engine or StandardDeduplicationEngine()

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[AsyncSession]:
        try:
            async with self.session_manager.session() as session:
                yield session
        except (DisconnectionError, InterfaceError, OperationalError, TimeoutError) as error:
            raise StorageUnavailable(type(error).__name__) from error

    async def contains(self, source: str, source_job_id: str) -> bool:
        return source_job_id in await self.contains_many(source, [source_job_id])

    async def contains_many(self, source: str, source_job_ids: list[str]) -> set[str]:
        if not source_job_ids:
            return set()
        found: set[str] = set()
        async with self._session() as session:
            for start in range(0, len(source_job_ids), 500):
                ids = source_job_ids[start:start + 500]
                stmt = select(JobModel.source_job_id).where(
                    JobModel.source == source, JobModel.source_job_id.in_(ids)
                ).union(
                    select(JobSightingModel.source_job_id).where(
                        JobSightingModel.source == source, JobSightingModel.source_job_id.in_(ids)
                    )
                )
                found.update((await session.execute(stmt)).scalars().all())
        return found

    async def save_batch(self, jobs: list[JobPosting]) -> int:
        if not jobs:
            return 0

        source_keys = list(dict.fromkeys((job.source, job.source_job_id) for job in jobs))
        source_names = {job.source for job in jobs}
        signatures = {self.dedup_engine.compute_canonical_signature(job) for job in jobs}
        earliest = min(job.posted_at for job in jobs) - timedelta(days=7)
        latest = max(job.posted_at for job in jobs) + timedelta(days=7)
        lock_keys = sorted(
            {
                int.from_bytes(sha256(signature.encode()).digest()[:8], "big", signed=True)
                for signature in signatures
            }
        )

        async with self._session() as session:
            await session.execute(
                text(
                    "SELECT pg_advisory_xact_lock(lock_key) "
                    "FROM unnest(CAST(:keys AS BIGINT[])) AS locks(lock_key) "
                    "ORDER BY lock_key"
                ),
                {"keys": lock_keys},
            )

            identity_jobs_result = await session.execute(
                select(JobModel).where(tuple_(JobModel.source, JobModel.source_job_id).in_(source_keys))
            )
            identity_jobs = identity_jobs_result.scalars().all()
            identity_sightings_result = await session.execute(
                select(JobSightingModel, JobModel)
                .join(JobModel, JobModel.id == JobSightingModel.job_id)
                .where(
                    tuple_(JobSightingModel.source, JobSightingModel.source_job_id).in_(source_keys)
                )
            )
            identity_sightings = identity_sightings_result.all()

            stmt = select(JobModel).where(
                JobModel.canonical_signature.in_(signatures),
                JobModel.posted_at.between(earliest, latest),
            ).order_by(JobModel.posted_at, JobModel.id)
            if len(source_names) == 1:
                stmt = stmt.where(JobModel.source != next(iter(source_names)))
            existing_results = await session.execute(stmt)
            existing_jobs = existing_results.scalars().all()

            models_by_id = {model.id: model for model in existing_jobs}
            models_by_id.update({model.id: model for model in identity_jobs})
            models_by_id.update({model.id: model for _, model in identity_sightings})
            candidates: list[tuple[JobPosting, uuid.UUID, JobModel | None]] = [
                (self._as_posting(model), model.id, model)
                for model in sorted(models_by_id.values(), key=lambda row: (row.posted_at, str(row.id)))
            ]
            refs_by_id = {candidate[1]: candidate for candidate in candidates}
            sources_by_canonical = {
                candidate[1]: {candidate[0].source} for candidate in candidates
            }
            if refs_by_id:
                represented_sources = await session.execute(
                    select(JobSightingModel.job_id, JobSightingModel.source).where(
                        JobSightingModel.job_id.in_(refs_by_id)
                    )
                )
                for job_id, source in represented_sources:
                    sources_by_canonical[job_id].add(source)
            candidates_by_signature: dict[
                str, dict[str, list[tuple[JobPosting, uuid.UUID, JobModel | None]]]
            ] = {}
            for candidate in candidates:
                signature = self.dedup_engine.compute_canonical_signature(candidate[0])
                candidates_by_signature.setdefault(signature, {}).setdefault(candidate[0].source, []).append(candidate)
            identity_map: dict[tuple[str, str], tuple[JobPosting, uuid.UUID, JobModel | None]] = {}
            for model in identity_jobs:
                identity_map[(model.source, model.source_job_id)] = refs_by_id[model.id]
            for sighting, model in identity_sightings:
                identity_map[(sighting.source, sighting.source_job_id)] = refs_by_id[model.id]

            records_by_id: dict[uuid.UUID, dict[str, object]] = {}
            new_ids_by_source: dict[tuple[str, str], uuid.UUID] = {}
            sightings_by_source: dict[tuple[str, str], dict[str, object]] = {}

            for job in jobs:
                source_key = (job.source, job.source_job_id)
                ref = identity_map.get(source_key)
                if ref is None:
                    signature = self.dedup_engine.compute_canonical_signature(job)
                    ref = next(
                        (candidate
                         for source, group in candidates_by_signature.get(signature, {}).items()
                         if source != job.source
                         for candidate in group
                         if job.source not in sources_by_canonical[candidate[1]]
                         and self.dedup_engine.is_duplicate(candidate[0], job)),
                        None,
                    )

                if ref is None:
                    new_id = uuid.uuid4()
                    simhash = self.dedup_engine.compute_simhash(job.description_text)
                    record: dict[str, object] = {
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
                        "canonical_signature": signature,
                        "simhash": simhash,
                        "attributes": job.attributes,
                    }
                    records_by_id[new_id] = record
                    new_ids_by_source[source_key] = new_id
                    ref = (job, new_id, None)
                    candidates_by_signature.setdefault(signature, {}).setdefault(job.source, []).append(ref)
                else:
                    canonical, canonical_id, canonical_model = ref
                    merged, changed = self.dedup_engine.enrich_attributes(canonical.attributes, job.attributes)
                    if changed:
                        canonical.attributes = merged
                        if canonical_model is not None:
                            canonical_model.attributes = merged
                        elif canonical_id in records_by_id:
                            records_by_id[canonical_id]["attributes"] = merged

                identity_map[source_key] = ref
                sources_by_canonical.setdefault(ref[1], set()).add(job.source)
                sightings_by_source.setdefault(
                    source_key,
                    {
                        "id": uuid.uuid4(),
                        "job_id": ref[1],
                        "source": job.source,
                        "source_job_id": job.source_job_id,
                        "source_url": job.source_url,
                        "seen_at": job.scraped_at,
                    },
                )

            inserted_by_source: dict[tuple[str, str], uuid.UUID] = {}
            inserted_count = 0
            if records_by_id:
                stmt_insert = insert(JobModel).values(list(records_by_id.values()))
                result = await session.execute(
                    stmt_insert.on_conflict_do_nothing().returning(
                        JobModel.id, JobModel.source, JobModel.source_job_id
                    )
                )
                inserted_rows = result.all()
                inserted_count = len(inserted_rows)
                inserted_by_source = {
                    (source, source_job_id): job_id
                    for job_id, source, source_job_id in inserted_rows
                }

                missing_keys = [key for key in new_ids_by_source if key not in inserted_by_source]
                if missing_keys:
                    rows = await session.execute(
                        select(JobModel.source, JobModel.source_job_id, JobModel.id).where(
                            tuple_(JobModel.source, JobModel.source_job_id).in_(missing_keys)
                        )
                    )
                    inserted_by_source.update(
                        {(source, source_job_id): job_id for source, source_job_id, job_id in rows.all()}
                    )

            id_remap = {
                proposed_id: inserted_by_source[source_key]
                for source_key, proposed_id in new_ids_by_source.items()
                if source_key in inserted_by_source
            }
            unresolved = [key for key in new_ids_by_source if key not in inserted_by_source]
            if unresolved:
                raise RuntimeError(f"Could not resolve stored job IDs for {len(unresolved)} source postings")

            sightings_to_insert = []
            for source_key, sighting in sightings_by_source.items():
                ref = identity_map[source_key]
                resolved_id = id_remap.get(ref[1], ref[1])
                sightings_to_insert.append({**sighting, "job_id": resolved_id})

            if sightings_to_insert:
                stmt_sightings = insert(JobSightingModel).values(sightings_to_insert)
                stmt_sightings = stmt_sightings.on_conflict_do_nothing(
                    constraint="uq_sightings_source_job_id"
                )
                await session.execute(stmt_sightings)

            await session.commit()

        return inserted_count

    @staticmethod
    def _as_posting(model: JobModel) -> JobPosting:
        return JobPosting.model_construct(
            source=model.source,
            source_job_id=model.source_job_id,
            source_url=model.source_url,
            title=model.title,
            company_name=model.company_name,
            description_text=model.description_text,
            posted_at=model.posted_at,
            scraped_at=model.scraped_at,
            content_hash=model.content_hash,
            attributes=model.attributes,
        )

    async def count(self) -> int:
        async with self._session() as session:
            stmt = select(func.count(JobModel.id))
            result = await session.execute(stmt)
            return result.scalar() or 0

