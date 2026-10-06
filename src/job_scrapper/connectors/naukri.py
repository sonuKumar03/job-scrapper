"""Naukri public jobs rendered through its JavaScript search page."""

import asyncio
import random
from typing import Any
from urllib.parse import urljoin

from job_scrapper.connectors.base import BaseConnector
from job_scrapper.domain.models import JobPosting
from job_scrapper.pipeline.cleaner import clean_html_to_text
from job_scrapper.pipeline.date_parser import is_within_days, parse_to_utc
from job_scrapper.storage.base import JobSink


class NaukriConnector(BaseConnector):
    name = "naukri"
    BASE_URL = "https://www.naukri.com"
    MAX_PAGES = 2000

    async def _fetch_job(self, page: Any, listing: dict[str, Any], posted_at: Any,
                         stats: dict[str, Any]) -> JobPosting | None:
        source_id = listing["jobId"]
        try:
            await asyncio.sleep(random.uniform(1, 3))
            async with page.expect_response(
                lambda response: f"/jobapi/v4/job/{source_id}" in response.url,
                timeout=30000,
            ) as response_info:
                await page.goto(urljoin(self.BASE_URL, listing["jdURL"]),
                                wait_until="domcontentloaded", timeout=30000)
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
            from playwright.async_api import async_playwright
        except ImportError as exc:
            self.record_error(stats, "browser", exc)
            stats["errors"].append("install the browser extra with uv sync --extra browser")
            return stats

        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(
                    headless=False,
                    channel="chrome",
                    args=["--disable-blink-features=AutomationControlled"],
                )
                try:
                    context = await browser.new_context()
                    search_page = await context.new_page()
                    detail_page = await context.new_page()
                    for page_number in range(self.MAX_PAGES):
                        if self.stop_requested:
                            break
                        url = (f"{self.BASE_URL}/software-engineer-jobs"
                               f"{'-' + str(page_number + 1) if page_number else ''}"
                               f"?k=software%20engineer&jobAge={max_days}")
                        try:
                            await asyncio.sleep(random.uniform(1, 3))
                            async with search_page.expect_response(
                                lambda response: "/jobapi/v3/search" in response.url,
                                timeout=30000,
                            ) as response_info:
                                await search_page.goto(url, wait_until="domcontentloaded",
                                                       timeout=30000)
                            response = await response_info.value
                            if response.status != 200:
                                raise ValueError(f"job search HTTP {response.status}")
                            data = await response.json()
                            listings = data.get("jobDetails")
                            if not isinstance(listings, list) or (page_number == 0 and not listings):
                                raise ValueError("no job search results")
                            fresh = [job for job in listings if isinstance(job, dict)
                                     and isinstance(job.get("jobId"), str)
                                     and isinstance(job.get("jdURL"), str)
                                     and job["jobId"] not in seen_ids]
                            seen_ids.update(job["jobId"] for job in fresh)
                        except Exception as exc:
                            self.record_error(stats, f"page {page_number + 1}", exc)
                            break
                        if not fresh:
                            break

                        stats["found"] += len(fresh)
                        known_ids = await sink.contains_many(self.name, [job["jobId"] for job in fresh])
                        jobs = []
                        for listing in fresh:
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
