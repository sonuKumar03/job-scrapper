"""Base connector abstraction for all job board scrapers."""

from abc import ABC, abstractmethod
from typing import Any
from job_scrapper.storage.base import JobSink
from job_scrapper.utils.http_client import ResilientHttpClient


class BaseConnector(ABC):
    """Abstract base class for all pluggable job board connectors."""

    name: str = "base"

    def __init__(self, http_client: ResilientHttpClient | None = None) -> None:
        self.http_client = http_client or ResilientHttpClient()

    @abstractmethod
    async def scrape(self, sink: JobSink, max_days: int = 7) -> dict[str, int]:
        """Execute the scrape run for this connector.

        Args:
            sink: Storage sink implementing JobSink protocol.
            max_days: Only include postings within the last max_days.

        Returns:
            Dict summarizing run: {"found": int, "inserted": int, "skipped": int}
        """
        pass
