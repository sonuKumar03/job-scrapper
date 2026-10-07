"""In-memory storage sink for zero-infrastructure testing and dry runs."""

from job_scrapper.domain.models import JobPosting
from job_scrapper.pipeline.dedup_engine import StandardDeduplicationEngine


class InMemoryJobSink:
    """Thread-safe in-memory sink that simulates database unique constraints."""

    def __init__(self) -> None:
        self.jobs_by_id: dict[tuple[str, str], JobPosting] = {}
        self.jobs: list[JobPosting] = []
        self.jobs_by_signature: dict[str, dict[str, list[JobPosting]]] = {}
        self.sources_by_canonical: dict[int, set[str]] = {}
        self.dedup_engine = StandardDeduplicationEngine()

    async def contains(self, source: str, source_job_id: str) -> bool:
        return (source, source_job_id) in self.jobs_by_id

    async def contains_many(self, source: str, source_job_ids: list[str]) -> set[str]:
        return {source_job_id for source_job_id in source_job_ids if (source, source_job_id) in self.jobs_by_id}

    async def save_batch(self, jobs: list[JobPosting]) -> int:
        new_count = 0
        for job in jobs:
            key = (job.source, job.source_job_id)
            canonical = self.jobs_by_id.get(key)
            signature = self.dedup_engine.compute_canonical_signature(job)
            if canonical is None:
                canonical = next(
                    (existing
                     for source, group in self.jobs_by_signature.get(signature, {}).items()
                     if source != job.source
                     for existing in group
                     if job.source not in self.sources_by_canonical[id(existing)]
                     and self.dedup_engine.is_duplicate(existing, job)),
                    None,
                )
            if canonical:
                merged, changed = self.dedup_engine.enrich_attributes(canonical.attributes, job.attributes)
                if changed:
                    canonical.attributes = merged
            else:
                canonical = job
                self.jobs.append(canonical)
                self.jobs_by_signature.setdefault(signature, {}).setdefault(job.source, []).append(canonical)
                new_count += 1
            self.jobs_by_id[key] = canonical
            self.sources_by_canonical.setdefault(id(canonical), set()).add(job.source)

        return new_count

    async def count(self) -> int:
        return len(self.jobs)

    def get_all(self) -> list[JobPosting]:
        return list(self.jobs)
