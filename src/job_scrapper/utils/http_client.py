"""Resilient HTTP client using curl_cffi for browser TLS impersonation."""

import asyncio
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from curl_cffi.requests import AsyncSession, Response
from job_scrapper.config import Settings, get_settings
from job_scrapper.execution.cancellation import RequestStopped, request_stop_event, wait_before_request


class RequestError(RuntimeError):
    """Safe request failure with no query string, credentials, or proxy details."""

    def __init__(self, url: str, reason: str, status_code: int | None = None) -> None:
        parsed = urlsplit(url)
        safe_netloc = parsed.netloc.rsplit("@", 1)[-1]
        safe_url = urlunsplit((parsed.scheme, safe_netloc, parsed.path, "", ""))
        self.status_code = status_code
        super().__init__(f"{reason}{f' (HTTP {status_code})' if status_code else ''}: {safe_url}")


@dataclass
class _DomainLimit:
    semaphore: asyncio.Semaphore
    start_lock: asyncio.Lock
    next_start: float = 0.0


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
        self.max_concurrency = settings.max_concurrent_requests
        self._domains: dict[str, _DomainLimit] = {}
        self.proxy = proxy if proxy is not None else defaults.http_proxy
        self.timeout = settings.request_timeout_seconds
        self._session: AsyncSession | None = None

    async def _get_session(self) -> AsyncSession:
        if self._session is None:
            self._session = AsyncSession(impersonate="chrome120")
        return self._session

    async def _request(self, method: str, url: str, **kwargs: Any) -> Response:
        """Issue a paced request with browser TLS impersonation and transient retries."""
        session = await self._get_session()
        kwargs.setdefault("timeout", self.timeout)
        if self.proxy:
            kwargs.setdefault("proxy", self.proxy)
        headers = kwargs.setdefault("headers", {})
        headers.setdefault(
            "Accept",
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,application/json,*/*;q=0.8",
        )
        headers.setdefault("Accept-Language", "en-US,en;q=0.9")
        host = urlsplit(url).hostname or ""
        domain = self._domains.get(host)
        if domain is None:
            domain = self._domains[host] = _DomainLimit(
                asyncio.Semaphore(self.max_concurrency), asyncio.Lock()
            )

        for attempt in range(3):
            if (stop := request_stop_event.get()) is not None and stop.is_set():
                raise RequestStopped()
            try:
                async with domain.semaphore:
                    async with domain.start_lock:
                        loop = asyncio.get_running_loop()
                        await wait_before_request(max(0.0, domain.next_start - loop.time()))
                        domain.next_start = loop.time() + random.uniform(self.min_delay, self.max_delay)
                    response = await session.request(method, url, **kwargs)
                if response.status_code not in {429, 500, 502, 503, 504}:
                    if response.status_code >= 400:
                        raise RequestError(url, "permanent HTTP failure", response.status_code)
                    return response
                retry_after = self._retry_after(response.headers.get("Retry-After"))
                if retry_after is None:
                    retry_after = float(attempt + 1)
                if retry_after > 120:
                    raise RequestError(url, "retry deferred by server", response.status_code)
            except (RequestError, RequestStopped):
                raise
            except Exception as exc:
                if attempt == 2:
                    raise RequestError(
                        url, f"transient request failed after 3 attempts ({type(exc).__name__})"
                    ) from None
                retry_after = float(attempt + 1)

            if attempt == 2:
                raise RequestError(url, "transient HTTP failure after 3 attempts", response.status_code)
            await wait_before_request(retry_after)
        raise AssertionError("unreachable")

    async def get(self, url: str, **kwargs: Any) -> Response:
        """Issue an async GET request with polite jitter and browser TLS impersonation."""
        return await self._request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> Response:
        """Issue an async POST request with the same pacing and retries as GET."""
        return await self._request("POST", url, **kwargs)

    @staticmethod
    def _retry_after(value: str | None) -> float | None:
        if not value:
            return None
        try:
            return max(0.0, float(int(value)))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(value)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
            except (TypeError, ValueError, OverflowError):
                return None

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None
