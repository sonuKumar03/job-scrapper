"""Base connector abstraction for all job board scrapers."""

import asyncio
from abc import ABC, abstractmethod
from typing import Any
from job_scrapper.domain.models import JobPosting
from job_scrapper.execution.contracts import HttpClient
from job_scrapper.storage.base import JobSink, StorageUnavailable
from job_scrapper.execution.cancellation import RequestStopped
from job_scrapper.utils.http_client import RequestError, ResilientHttpClient


class BaseConnector(ABC):
    """Abstract base class for all pluggable job board connectors."""

    name: str = "base"

    def __init__(self, http_client: HttpClient | None = None) -> None:
        self.stop_event: asyncio.Event | None = None
        self._owns_http_client = http_client is None
        self.http_client = http_client if http_client is not None else ResilientHttpClient()

    @property
    def stop_requested(self) -> bool:
        """Cooperative stop checked between pages or company batches."""
        return self.stop_event is not None and self.stop_event.is_set()

    async def close(self) -> None:
        """Close an owned client; injected shared clients belong to their creator."""
        if self._owns_http_client:
            await self.http_client.close()

    @abstractmethod
    async def scrape(self, sink: JobSink, max_days: int = 7) -> dict[str, Any]:
        """Execute the scrape run for this connector.

        Args:
            sink: Storage sink implementing JobSink protocol.
            max_days: Only include postings within the last max_days.

        Returns:
            Counts plus source-level errors and whether coverage was incomplete.
        """
        pass

    @staticmethod
    def new_stats() -> dict[str, Any]:
        return {"found": 0, "inserted": 0, "skipped": 0, "errors": [], "truncated": False}

    @staticmethod
    def record_error(stats: dict[str, Any], context: str, error: Exception) -> None:
        if isinstance(error, RequestStopped):
            return
        if isinstance(error, StorageUnavailable):
            raise error
        reason = str(error) if isinstance(error, RequestError) else type(error).__name__
        stats["errors"].append(f"{context}: {reason}")
        stats["truncated"] = True

    @staticmethod
    def record_unknown_dates(stats: dict[str, Any], context: str, count: int) -> None:
        if count:
            stats["errors"].append(f"{context}: {count} listings had unknown or invalid publication dates")
            stats["truncated"] = True

    @staticmethod
    def record_account_stats(
        aggregate: dict[str, Any], account_key: str, account_stats: dict[str, Any]
    ) -> None:
        """Merge one account's counts and errors into provider-level statistics."""
        account_row = {
            "found": account_stats["found"],
            "inserted": account_stats["inserted"],
            "skipped": account_stats["skipped"],
            "errors": list(account_stats["errors"]),
            "truncated": account_stats["truncated"],
        }
        aggregate.setdefault("accounts", {})[account_key] = account_row
        aggregate["found"] += account_row["found"]
        aggregate["inserted"] += account_row["inserted"]
        aggregate["skipped"] += account_row["skipped"]
        aggregate["errors"].extend(
            f"company {account_key}: {error}" for error in account_row["errors"]
        )
        aggregate["truncated"] |= account_row["truncated"]

    @staticmethod
    async def save_jobs(sink: JobSink, jobs: list[JobPosting], stats: dict[str, Any]) -> None:
        for start in range(0, len(jobs), 500):
            batch = jobs[start:start + 500]
            inserted = await sink.save_batch(batch)
            stats["inserted"] += inserted
            stats["skipped"] += len(batch) - inserted
