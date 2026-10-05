"""Jobicy remote jobs connector."""

from typing import Any
from job_scrapper.connectors.base import BaseConnector
from job_scrapper.domain.models import JobPosting
from job_scrapper.pipeline.cleaner import clean_html_to_text
from job_scrapper.pipeline.date_parser import is_within_days, parse_to_utc
from job_scrapper.storage.base import JobSink


class JobicyConnector(BaseConnector):
    name: str = "jobicy"
    API_URL: str = "https://jobicy.com/api/v2/remote-jobs"

    async def scrape(self, sink: JobSink, max_days: int = 7) -> dict[str, int]:
        stats = {"found": 0, "inserted": 0, "skipped": 0}

        response = await self.http_client.get(f"{self.API_URL}?count=50")
        if response.status_code != 200:
            return stats

        data = response.json()
        raw_jobs = data.get("jobs", [])
        batch: list[JobPosting] = []

        for item in raw_jobs:
            stats["found"] += 1
            source_id = str(item.get("id"))

            # Check publication date
            pub_date = parse_to_utc(item.get("pubDate"))
            if not pub_date or not is_within_days(pub_date, max_days=max_days):
                stats["skipped"] += 1
                continue

            # Quick pre-fetch check
            if await sink.contains(self.name, source_id):
                stats["skipped"] += 1
                continue

            raw_desc = item.get("jobDescription") or item.get("jobExcerpt") or ""
            clean_desc = clean_html_to_text(raw_desc)

            # Build extensible attributes for classification
            attributes: dict[str, Any] = {
                "seniority": item.get("jobLevel"),
                "work_arrangement": "remote",
                "location": item.get("jobGeo"),
                "salary_min": item.get("salaryMin"),
                "salary_max": item.get("salaryMax"),
                "currency": item.get("salaryCurrency"),
                "tech_stack": [item.get("jobIndustry")] if item.get("jobIndustry") else [],
                "employment_type": item.get("jobType"),
            }

            job = JobPosting(
                source=self.name,
                source_job_id=source_id,
                source_url=item.get("url") or "",
                title=item.get("jobTitle") or "Untitled",
                company_name=item.get("companyName") or "Unknown Company",
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
