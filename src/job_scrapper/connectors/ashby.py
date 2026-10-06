"""Published employer postings from Ashby's public job-board API."""

import asyncio
from typing import Any

from job_scrapper.connectors.base import BaseConnector
from job_scrapper.domain.models import JobPosting
from job_scrapper.pipeline.cleaner import clean_html_to_text
from job_scrapper.pipeline.date_parser import is_within_days, parse_to_utc
from job_scrapper.storage.base import JobSink


DEFAULT_ASHBY_COMPANIES = {
    "openai": "OpenAI",
    "supabase": "Supabase",
    "ramp": "Ramp",
    "linear": "Linear",
    "notion": "Notion",
    "perplexity": "Perplexity",
    "cursor": "Cursor",
    "ashby": "Ashby",
}


class AshbyConnector(BaseConnector):
    name = "ashby"
    BASE_URL = "https://api.ashbyhq.com/posting-api/job-board"

    def __init__(self, companies: dict[str, str] | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.companies = companies if companies is not None else DEFAULT_ASHBY_COMPANIES

    async def scrape(self, sink: JobSink, max_days: int = 7) -> dict[str, Any]:
        stats = self.new_stats()

        async def scrape_company(slug: str, company_name: str) -> None:
            try:
                response = await self.http_client.get(f"{self.BASE_URL}/{slug}")
                data = response.json()
                jobs = data.get("jobs") if isinstance(data, dict) else None
                if not isinstance(jobs, list) or any(not isinstance(job, dict) for job in jobs):
                    raise ValueError("response jobs must be a list of objects")
            except Exception as exc:
                self.record_error(stats, f"company {slug}", exc)
                return

            listed = [job for job in jobs if job.get("isListed") is not False]
            known_ids = await sink.contains_many(
                self.name, [job["id"] for job in listed if isinstance(job.get("id"), str)]
            )
            batch: list[JobPosting] = []
            unknown_dates = 0
            invalid = 0
            for item in listed:
                stats["found"] += 1
                source_id = item.get("id")
                pub_date = parse_to_utc(item.get("publishedAt"))
                if not pub_date:
                    unknown_dates += 1
                    stats["skipped"] += 1
                    continue
                if not is_within_days(pub_date, max_days=max_days) or source_id in known_ids:
                    stats["skipped"] += 1
                    continue

                description = item.get("descriptionPlain") or clean_html_to_text(item.get("descriptionHtml") or "")
                if not all(isinstance(value, str) and value.strip() for value in
                           (source_id, item.get("jobUrl"), item.get("title"), description)):
                    invalid += 1
                    stats["skipped"] += 1
                    continue

                arrangement = (item.get("workplaceType") or "unknown").lower()
                if arrangement == "onsite":
                    arrangement = "in-office"
                batch.append(JobPosting(
                    source=self.name,
                    source_job_id=source_id,
                    source_url=item["jobUrl"],
                    title=item["title"],
                    company_name=company_name,
                    description_text=description,
                    posted_at=pub_date,
                    attributes={
                        "work_arrangement": arrangement,
                        "location": item.get("location"),
                        "department": item.get("department"),
                        "team": item.get("team"),
                        "employment_type": item.get("employmentType"),
                        "company_slug": slug,
                    },
                ))

            await self.save_jobs(sink, batch, stats)
            self.record_unknown_dates(stats, f"company {slug}", unknown_dates)
            if invalid:
                self.record_error(stats, f"company {slug}", ValueError(f"{invalid} listed jobs lacked required fields"))

        companies = list(self.companies.items())
        for start in range(0, len(companies), 3):
            await asyncio.gather(*(scrape_company(slug, name) for slug, name in companies[start:start + 3]))
        return stats
