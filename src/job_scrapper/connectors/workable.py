"""Public job listings from Workable company career pages."""

import asyncio
from typing import Any

from job_scrapper.connectors.base import BaseConnector
from job_scrapper.connectors.company_sources import load_company_sources
from job_scrapper.domain.models import JobPosting
from job_scrapper.pipeline.cleaner import clean_html_to_text
from job_scrapper.pipeline.date_parser import parse_to_utc
from job_scrapper.storage.base import JobSink


class WorkableConnector(BaseConnector):
    name = "workable"
    BASE_URL = "https://apply.workable.com/api/v1/widget/accounts"

    def __init__(self, companies: dict[str, str] | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.companies = companies if companies is not None else {
            source.account_key: source.company_name
            for source in load_company_sources(self.name)
            if source.status == "supported" and source.account_key
        }

    async def scrape(self, sink: JobSink, max_days: int = 7) -> dict[str, Any]:
        stats = self.new_stats()

        async def scrape_company(account: str, name: str) -> None:
            row = self.new_stats()
            try:
                response = await self.http_client.get(f"{self.BASE_URL}/{account}?details=true")
                data = response.json()
                jobs = data.get("jobs") if isinstance(data, dict) else None
                if not isinstance(jobs, list) or any(not isinstance(job, dict) for job in jobs):
                    raise ValueError("response jobs must be a list of objects")
                ids = [f"{account}:{job.get('id') or job.get('shortcode')}" for job in jobs
                       if job.get("id") is not None or job.get("shortcode")]
                known = await sink.contains_many(self.name, ids)
                batch: list[JobPosting] = []
                missing_dates = 0
                for item in jobs:
                    row["found"] += 1
                    raw_id = item.get("id") or item.get("shortcode")
                    source_id = f"{account}:{raw_id}" if raw_id is not None else None
                    posted = parse_to_utc(item.get("published_on") or item.get("created_at"))
                    if not posted:
                        missing_dates += 1
                        row["skipped"] += 1
                        continue
                    if source_id in known:
                        row["skipped"] += 1
                        continue
                    title = item.get("title")
                    url = item.get("url") or item.get("shortlink") or item.get("application_url")
                    description = clean_html_to_text(item.get("description") or "")
                    if not all(isinstance(value, str) and value.strip() for value in (source_id, title, url, description)):
                        row["skipped"] += 1
                        row["errors"].append("listing missing required fields")
                        row["truncated"] = True
                        continue
                    location = item.get("location")
                    workplace_type = item.get("workplace_type")
                    if isinstance(location, dict):
                        workplace_type = location.get("workplace_type") or workplace_type
                        location = location.get("location_str")
                    batch.append(JobPosting(
                        source=self.name, source_job_id=source_id, source_url=url, title=title,
                        company_name=name, description_text=description, posted_at=posted,
                        attributes={"location": location, "work_arrangement": workplace_type,
                                    "company_slug": account},
                    ))
                await self.save_jobs(sink, batch, row)
                self.record_unknown_dates(row, "listing", missing_dates)
            except Exception as exc:
                self.record_error(row, "listing", exc)
            self.record_account_stats(stats, account, row)

        companies = list(self.companies.items())
        for start in range(0, len(companies), 3):
            if self.stop_requested:
                break
            await asyncio.gather(*(scrape_company(*entry) for entry in companies[start:start + 3]))
        return stats
