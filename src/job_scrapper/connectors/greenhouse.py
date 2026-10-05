"""Greenhouse ATS direct employer board connector."""

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
    "supabase",
    "cloudflare",
    "airbnb",
    "databricks",
    "retool",
    "openai",
    "anthropic",
    "scaleai",
    "datadog",
    "elastic",
    "automattic",
    "coinbase",
    "dropbox",
    "instacart",
    "robinhood",
    "affirm",
    "brex",
    "ramp",
    "dbtlabs",
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

    async def scrape(self, sink: JobSink, max_days: int = 7) -> dict[str, int]:
        stats = {"found": 0, "inserted": 0, "skipped": 0}

        for company in self.companies:
            url = f"{self.BASE_URL}/{company}/jobs?content=true"
            try:
                response = await self.http_client.get(url)
                if response.status_code != 200:
                    continue

                data = response.json()
                raw_jobs = data.get("jobs", [])
            except Exception:
                continue

            batch: list[JobPosting] = []

            for item in raw_jobs:
                stats["found"] += 1
                source_id = str(item.get("id"))

                raw_date = item.get("updated_at") or item.get("first_published")
                pub_date = parse_to_utc(raw_date)
                if not pub_date or not is_within_days(pub_date, max_days=max_days):
                    stats["skipped"] += 1
                    continue

                if source_id and await sink.contains(self.name, source_id):
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

            if batch:
                inserted = await sink.save_batch(batch)
                stats["inserted"] += inserted
                stats["skipped"] += len(batch) - inserted

        return stats
