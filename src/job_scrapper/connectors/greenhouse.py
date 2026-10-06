"""Greenhouse ATS direct employer board connector."""

import asyncio
import html
from typing import Any
from job_scrapper.connectors.base import BaseConnector
from job_scrapper.domain.models import JobPosting
from job_scrapper.pipeline.cleaner import clean_html_to_text
from job_scrapper.pipeline.date_parser import is_within_days, parse_to_utc
from job_scrapper.storage.base import JobSink

# Curated list of prominent companies using Greenhouse
DEFAULT_GREENHOUSE_COMPANIES = [
    "gitlab",
    "figma",
    "vercel",
    "webflow",
    "cloudflare",
    "airbnb",
    "databricks",
    "asana",
    "duolingo",
    "anthropic",
    "scaleai",
    "datadog",
    "elastic",
    "stripe",
    "coinbase",
    "dropbox",
    "instacart",
    "robinhood",
    "affirm",
    "brex",
    "reddit",
    "mongodb",
    "gusto",
    "carta",
    "checkr",
]


class GreenhouseConnector(BaseConnector):
    name: str = "greenhouse"
    BASE_URL: str = "https://boards-api.greenhouse.io/v1/boards"

    def __init__(self, companies: list[str] | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.companies = companies or DEFAULT_GREENHOUSE_COMPANIES

    async def scrape(self, sink: JobSink, max_days: int = 7) -> dict[str, Any]:
        stats = self.new_stats()

        async def scrape_company(company: str) -> None:
            unknown_dates = 0
            url = f"{self.BASE_URL}/{company}/jobs?content=true"
            try:
                response = await self.http_client.get(url)
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError("response must be an object")
                raw_jobs = data.get("jobs")
                if not isinstance(raw_jobs, list) or any(not isinstance(item, dict) for item in raw_jobs):
                    raise ValueError("response jobs must be a list of objects")
            except Exception as exc:
                self.record_error(stats, f"company {company}", exc)
                return

            batch: list[JobPosting] = []
            known_ids = await sink.contains_many(
                self.name, [str(item["id"]) for item in raw_jobs if item.get("id") is not None]
            )

            for item in raw_jobs:
                stats["found"] += 1
                source_id = str(item.get("id"))

                pub_date = parse_to_utc(item.get("first_published"))
                if not pub_date:
                    unknown_dates += 1
                    stats["skipped"] += 1
                    continue
                if not is_within_days(pub_date, max_days=max_days):
                    stats["skipped"] += 1
                    continue

                if source_id in known_ids:
                    stats["skipped"] += 1
                    continue

                raw_content = html.unescape(item.get("content") or "")
                clean_desc = clean_html_to_text(raw_content)

                location_dict = item.get("location") or {}
                location_str = location_dict.get("name") if isinstance(location_dict, dict) else str(location_dict)

                work_arrangement = "unknown"
                loc_lower = (location_str or "").lower()
                if "remote" in loc_lower:
                    work_arrangement = "remote"
                elif "hybrid" in loc_lower:
                    work_arrangement = "hybrid"
                elif loc_lower:
                    work_arrangement = "in-office"

                depts = [d.get("name") for d in item.get("departments", []) if d.get("name")]

                attributes: dict[str, Any] = {
                    "work_arrangement": work_arrangement,
                    "location": location_str,
                    "departments": depts,
                    "company_slug": company,
                }

                company_name = item.get("company_name") or company.capitalize()

                job = JobPosting(
                    source=self.name,
                    source_job_id=source_id,
                    source_url=item.get("absolute_url") or f"https://boards.greenhouse.io/{company}/jobs/{source_id}",
                    title=item.get("title") or "Untitled",
                    company_name=company_name,
                    description_text=clean_desc,
                    posted_at=pub_date,
                    attributes=attributes,
                )
                batch.append(job)

            await self.save_jobs(sink, batch, stats)
            self.record_unknown_dates(stats, f"company {company}", unknown_dates)

        for start in range(0, len(self.companies), 3):
            companies = self.companies[start:start + 3]
            results = await asyncio.gather(
                *(scrape_company(company) for company in companies), return_exceptions=True
            )
            for company, result in zip(companies, results):
                if isinstance(result, Exception):
                    self.record_error(stats, f"company {company}", result)
        return stats
