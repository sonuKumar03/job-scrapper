"""Resilient HTTP client using curl_cffi for browser TLS impersonation."""

import asyncio
import os
import random
from typing import Any
from curl_cffi.requests import AsyncSession, Response


class ResilientHttpClient:
    """Async HTTP client that mimics Chrome TLS handshakes and enforces polite delays."""

    def __init__(
        self,
        min_delay: float = 1.0,
        max_delay: float = 2.5,
        max_concurrency: int = 3,
        proxy: str | None = None,
        timeout: int = 30,
    ) -> None:
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.proxy = proxy or os.getenv("HTTP_PROXY") or None
        self.timeout = timeout
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
