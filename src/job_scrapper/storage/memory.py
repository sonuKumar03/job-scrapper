"""In-memory storage sink for zero-infrastructure testing and dry runs."""

from job_scrapper.domain.models import JobPosting


class InMemoryJobSink:
    """Thread-safe in-memory sink that simulates database unique constraints."""

    def __init__(self) -> None:
        self.jobs_by_id: dict[tuple[str, str], JobPosting] = {}
        self.jobs_by_hash: dict[str, JobPosting] = {}

    async def contains(self, source: str, source_job_id: str) -> bool:
        return (source, source_job_id) in self.jobs_by_id

    async def save_batch(self, jobs: list[JobPosting]) -> int:
        new_count = 0
        for job in jobs:
            key = (job.source, job.source_job_id)
            if key in self.jobs_by_id or job.content_hash in self.jobs_by_hash:
                continue

            self.jobs_by_id[key] = job
            self.jobs_by_hash[job.content_hash] = job
            new_count += 1

        return new_count

    async def count(self) -> int:
        return len(self.jobs_by_id)

    def get_all(self) -> list[JobPosting]:
        return list(self.jobs_by_id.values())
