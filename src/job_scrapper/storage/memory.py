"""In-memory storage sink for zero-infrastructure testing and dry runs."""

from job_scrapper.domain.models import JobPosting
from job_scrapper.pipeline.dedup_engine import StandardDeduplicationEngine


class InMemoryJobSink:
    """Thread-safe in-memory sink that simulates database unique constraints."""

    def __init__(self) -> None:
        self.jobs_by_id: dict[tuple[str, str], JobPosting] = {}
        self.jobs: list[JobPosting] = []
        self.dedup_engine = StandardDeduplicationEngine()

    async def contains(self, source: str, source_job_id: str) -> bool:
        return (source, source_job_id) in self.jobs_by_id

    async def save_batch(self, jobs: list[JobPosting]) -> int:
        new_count = 0
        for job in jobs:
            key = (job.source, job.source_job_id)
            if key in self.jobs_by_id:
                continue

            canonical = next(
                (existing for existing in self.jobs if self.dedup_engine.is_duplicate(existing, job)),
                None,
            )
            if canonical:
                merged, changed = self.dedup_engine.enrich_attributes(canonical.attributes, job.attributes)
                if changed:
                    canonical.attributes = merged
            else:
                canonical = job
                self.jobs.append(canonical)
                new_count += 1
            self.jobs_by_id[key] = canonical

        return new_count

    async def count(self) -> int:
        return len(self.jobs)

    def get_all(self) -> list[JobPosting]:
        return list(self.jobs)
