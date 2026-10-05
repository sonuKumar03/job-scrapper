"""Resilient HTTP client using curl_cffi for browser TLS impersonation."""

import asyncio
import random
from typing import Any
from curl_cffi.requests import AsyncSession, Response
from job_scrapper.config import Settings, get_settings


class ResilientHttpClient:
    """Async HTTP client that mimics Chrome TLS handshakes and enforces polite delays."""

    def __init__(
        self,
        min_delay: float | None = None,
        max_delay: float | None = None,
        max_concurrency: int | None = None,
        proxy: str | None = None,
        timeout: int | None = None,
    ) -> None:
        defaults = get_settings()
        settings = Settings(
            min_request_delay_seconds=(
                defaults.min_request_delay_seconds if min_delay is None else min_delay
            ),
            max_request_delay_seconds=(
                defaults.max_request_delay_seconds if max_delay is None else max_delay
            ),
            max_concurrent_requests=(
                defaults.max_concurrent_requests if max_concurrency is None else max_concurrency
            ),
            request_timeout_seconds=(
                defaults.request_timeout_seconds if timeout is None else timeout
            ),
        )
        self.min_delay = settings.min_request_delay_seconds
        self.max_delay = settings.max_request_delay_seconds
        self.semaphore = asyncio.Semaphore(settings.max_concurrent_requests)
        self.proxy = proxy if proxy is not None else defaults.http_proxy
        self.timeout = settings.request_timeout_seconds
        self._session: AsyncSession | None = None

    async def _get_session(self) -> AsyncSession:
        if self._session is None:
            self._session = AsyncSession(impersonate="chrome120")
        return self._session

    async def get(self, url: str, **kwargs: Any) -> Response:
        """Issue an async GET request with polite jitter and browser TLS impersonation."""
        session = await self._get_session()

        async with self.semaphore:
            # Polite jitter to avoid rate-limiting on local IP
            delay = random.uniform(self.min_delay, self.max_delay)
            await asyncio.sleep(delay)

            kwargs.setdefault("timeout", self.timeout)
            if self.proxy:
                kwargs.setdefault("proxy", self.proxy)

            headers = kwargs.setdefault("headers", {})
            headers.setdefault(
                "Accept",
                "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,application/json,*/*;q=0.8",
            )
            headers.setdefault("Accept-Language", "en-US,en;q=0.9")

            response = await session.get(url, **kwargs)
            return response

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None
