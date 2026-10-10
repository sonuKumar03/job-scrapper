"""Naukri public jobs rendered through its JavaScript search page."""

import asyncio
import random
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

from job_scrapper.connectors.base import BaseConnector
from job_scrapper.domain.models import JobPosting
from job_scrapper.pipeline.cleaner import clean_html_to_text
from job_scrapper.pipeline.date_parser import is_within_days, parse_to_utc
from job_scrapper.storage.base import JobSink
from job_scrapper.execution.contracts import SourceUnavailable
from job_scrapper.utils.http_client import RequestError


class NaukriConnector(BaseConnector):
    name = "naukri"
    BASE_URL = "https://www.naukri.com"
    MAX_PAGES = 2000
    SEARCH_TIMEOUT_MS = 60000

    async def check_prerequisites(self) -> None:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise SourceUnavailable('Naukri requires: uv sync --extra browser; then uv run playwright install --with-deps chromium') from None
        async with async_playwright() as playwright:
            if not Path(playwright.chromium.executable_path).is_file():
                raise SourceUnavailable('Naukri Chromium is missing: uv run --extra browser playwright install --with-deps chromium')
            try:
                browser = await playwright.chromium.launch(headless=True, channel='chromium')
                await browser.close()
            except Exception as error:
                raise SourceUnavailable(f'Naukri Chromium cannot start ({type(error).__name__}); rebuild the worker or run playwright install --with-deps chromium') from None

    @staticmethod
    async def _navigate_page(page: Any, url: str, timeout: int) -> Any:
        response = await page.goto(url, wait_until='domcontentloaded', timeout=timeout)
        if response is not None and response.status >= 400:
            raise RequestError(url, 'browser navigation rejected', response.status)
        return response

    async def _fetch_job(self, page: Any, listing: dict[str, Any], posted_at: Any,
                         stats: dict[str, Any]) -> JobPosting | None:
        if self.stop_requested:
            return None
        source_id = listing["jobId"]
        try:
            await asyncio.sleep(random.uniform(1, 3))
            if self.stop_requested:
                return None
            async with page.expect_response(
                lambda response: f"/jobapi/v4/job/{source_id}" in response.url,
                timeout=30000,
            ) as response_info:
                await self._navigate_page(page, urljoin(self.BASE_URL, listing["jdURL"]), 30000)
            response = await response_info.value
            if response.status != 200:
                raise ValueError(f"job detail HTTP {response.status}")
            item = (await response.json())["jobDetails"]
            if item.get("jobId") != source_id:
                raise ValueError("job detail ID mismatch")
            organization = item.get("companyDetail") or {}
            company = organization.get("name") if isinstance(organization, dict) else None
            description = clean_html_to_text(item.get("description") or "")
            if not all(isinstance(value, str) and value.strip() for value in
                       (item.get("title"), company, description)):
                raise ValueError("missing title, company, or description")
            locations = item.get("locations") or []
            return JobPosting(
                source=self.name,
                source_job_id=source_id,
                source_url=urljoin(self.BASE_URL, listing["jdURL"]),
                title=item["title"],
                company_name=company,
                description_text=description,
                posted_at=posted_at,
                attributes={
                    "location": ", ".join(place["label"] for place in locations
                                          if isinstance(place, dict) and place.get("label")) or None,
                    "employment_type": item.get("employmentType"),
                    "experience_years_min": item.get("minimumExperience"),
                    "experience_years_max": item.get("maximumExperience"),
                    "work_arrangement": {"2": "remote", "3": "hybrid", "0": "in-office"}.get(
                        str(item.get("wfhType")), "unknown"
                    ),
                },
            )
        except Exception as exc:
            self.record_error(stats, f"job {source_id}", exc)
            stats["skipped"] += 1
            return None

    async def scrape(self, sink: JobSink, max_days: int = 7) -> dict[str, Any]:
        stats = self.new_stats()
        seen_ids: set[str] = set()
        try:
            from playwright.async_api import TimeoutError as BrowserTimeoutError, async_playwright
        except ImportError as exc:
            self.record_error(stats, "browser", exc)
            stats["errors"].append("install the browser extra with uv sync --extra browser")
            return stats

        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(
                    headless=True,
                    channel='chromium',
                    args=["--disable-blink-features=AutomationControlled"],
                )
                try:
                    # Use full Chromium with a normal UA; HeadlessChrome search navigation is denied.
                    context = await browser.new_context(user_agent=(
                        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                        f'(KHTML, like Gecko) Chrome/{browser.version} Safari/537.36'
                    ))
                    search_page = await context.new_page()
                    detail_page = await context.new_page()
                    failed_requests: list[str] = []

                    def record_failed_request(request: Any) -> None:
                        if request.resource_type in ('document', 'script', 'xhr', 'fetch') and len(failed_requests) < 5:
                            parsed = urlsplit(request.url)
                            failed_requests.append(f'{parsed.netloc}{parsed.path}: {request.failure}')

                    search_page.on('requestfailed', record_failed_request)
                    for page_number in range(self.MAX_PAGES):
                        if self.stop_requested:
                            break
                        url = (f"{self.BASE_URL}/software-engineer-jobs"
                               f"{'-' + str(page_number + 1) if page_number else ''}"
                               f"?k=software%20engineer&jobAge={max_days}")
                        navigation_response = None
                        failed_requests.clear()
                        try:
                            await asyncio.sleep(random.uniform(1, 3))
                            if self.stop_requested:
                                break
                            async with search_page.expect_response(
                                lambda response: "/jobapi/v3/search" in response.url,
                                timeout=self.SEARCH_TIMEOUT_MS,
                            ) as response_info:
                                navigation_response = await self._navigate_page(
                                    search_page, url, self.SEARCH_TIMEOUT_MS)
                            response = await response_info.value
                            if response.status != 200:
                                raise ValueError(f"job search HTTP {response.status}")
                            data = await response.json()
                            listings = data.get("jobDetails")
                            if not isinstance(listings, list) or (page_number == 0 and not listings):
                                raise ValueError("no job search results")
                            valid = [job for job in listings if isinstance(job, dict)
                                     and isinstance(job.get("jobId"), str) and job["jobId"].strip()
                                     and isinstance(job.get("jdURL"), str) and job["jdURL"].strip()]
                            invalid = len(listings) - len(valid)
                            if invalid:
                                stats["found"] += invalid
                                stats["skipped"] += invalid
                                self.record_error(stats, f"page {page_number + 1}: {invalid} listings lacked valid identities",
                                                  ValueError("invalid jobId or jdURL"))
                            fresh = [job for job in valid if job["jobId"] not in seen_ids]
                            seen_ids.update(job["jobId"] for job in fresh)
                        except Exception as exc:
                            self.record_error(stats, f"page {page_number + 1}", exc)
                            if isinstance(exc, BrowserTimeoutError):
                                stats['errors'][-1] = f'page {page_number + 1}: {type(exc).__name__}: {exc}'
                                try:
                                    title = await asyncio.wait_for(search_page.title(), timeout=2)
                                except Exception:
                                    title = 'unavailable'
                                status = navigation_response.status if navigation_response is not None else 'unknown'
                                stats['errors'].append(
                                    f'page {page_number + 1} diagnostics: URL={search_page.url}; title={title}; '
                                    f'document HTTP={status}; failed requests={"; ".join(failed_requests) or "none observed"}'
                                )
                            break
                        if not fresh:
                            if valid:
                                stats["truncated"] = True
                                stats["errors"].append(f"page {page_number + 1}: repeated listings; coverage incomplete")
                            break

                        stats["found"] += len(fresh)
                        known_ids = await sink.contains_many(self.name, [job["jobId"] for job in fresh])
                        jobs = []
                        for listing in fresh:
                            if self.stop_requested:
                                break
                            if listing["jobId"] in known_ids:
                                stats["skipped"] += 1
                                continue
                            posted_at = parse_to_utc(listing.get("createdDate"))
                            if posted_at is None:
                                self.record_unknown_dates(stats, f"job {listing['jobId']}", 1)
                                stats["skipped"] += 1
                            elif is_within_days(posted_at, max_days):
                                job = await self._fetch_job(detail_page, listing, posted_at, stats)
                                if job is not None:
                                    jobs.append(job)
                            else:
                                stats["skipped"] += 1
                        await self.save_jobs(sink, jobs, stats)
                        if page_number * 20 + len(listings) >= data.get("noOfJobs", 0):
                            break
                    else:
                        stats["truncated"] = True
                        stats["errors"].append(f"page safety limit reached ({self.MAX_PAGES} pages)")
                finally:
                    await browser.close()
        except Exception as exc:
            self.record_error(stats, "browser", exc)
        return stats
