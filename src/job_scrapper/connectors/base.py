"""Base connector abstraction for all job board scrapers."""

from abc import ABC, abstractmethod
from typing import Any
from job_scrapper.storage.base import JobSink
from job_scrapper.utils.http_client import RequestError, ResilientHttpClient


class BaseConnector(ABC):
    """Abstract base class for all pluggable job board connectors."""

    name: str = "base"

    def __init__(self, http_client: ResilientHttpClient | None = None) -> None:
        self.http_client = http_client or ResilientHttpClient()

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
        reason = str(error) if isinstance(error, RequestError) else type(error).__name__
        stats["errors"].append(f"{context}: {reason}")
        stats["truncated"] = True

    @staticmethod
    def record_unknown_dates(stats: dict[str, Any], context: str, count: int) -> None:
        if count:
            stats["errors"].append(f"{context}: {count} listings had unknown or invalid publication dates")
            stats["truncated"] = True
