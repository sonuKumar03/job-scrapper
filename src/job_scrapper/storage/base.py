"""Storage abstraction layer (Ports & Adapters)."""

from typing import Protocol, runtime_checkable
from job_scrapper.domain.models import JobPosting


class StorageUnavailable(RuntimeError):
    """A transient storage failure that must escape connector error handling."""


@runtime_checkable
class JobSink(Protocol):
    """Abstract sink interface to decouple connectors from databases."""

    async def contains(self, source: str, source_job_id: str) -> bool:
        """Check if a job has already been scraped to avoid fetching detail pages."""
        ...

    async def contains_many(self, source: str, source_job_ids: list[str]) -> set[str]:
        """Return stored identities from a page or bounded batch."""
        ...

    async def save_batch(self, jobs: list[JobPosting]) -> int:
        """Save a batch of jobs.

        Returns:
            Number of newly inserted (non-duplicate) jobs.
        """
        ...

    async def count(self) -> int:
        """Return total number of stored jobs."""
        ...
