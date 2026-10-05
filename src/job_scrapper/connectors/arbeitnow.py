"""Arbeitnow job board connector with pagination."""

from typing import Any
from job_scrapper.connectors.base import BaseConnector
from job_scrapper.domain.models import JobPosting
from job_scrapper.pipeline.cleaner import clean_html_to_text
from job_scrapper.pipeline.date_parser import is_within_days, parse_to_utc
from job_scrapper.storage.base import JobSink


class ArbeitnowConnector(BaseConnector):
    name: str = "arbeitnow"
    API_URL: str = "https://www.arbeitnow.com/api/job-board-api"

    async def scrape(self, sink: JobSink, max_days: int = 7) -> dict[str, int]:
        stats = {"found": 0, "inserted": 0, "skipped": 0}
        page = 1
        max_pages = 50  # Up to 50 pages (~5,000+ jobs)

        while page <= max_pages:
            url = f"{self.API_URL}?page={page}"
            response = await self.http_client.get(url)
            if response.status_code != 200:
                break

            data = response.json()
            items = data.get("data", [])
            if not items:
                break

            batch: list[JobPosting] = []
            reached_cutoff = False

            for item in items:
                stats["found"] += 1
                slug = item.get("slug")
                if not slug:
                    stats["skipped"] += 1
                    continue

                created_at = item.get("created_at")
                pub_date = parse_to_utc(created_at)
                if not pub_date:
                    stats["skipped"] += 1
                    continue

                if not is_within_days(pub_date, max_days=max_days):
                    stats["skipped"] += 1
                    reached_cutoff = True
                    continue

                if await sink.contains(self.name, slug):
                    stats["skipped"] += 1
                    continue

                clean_desc = clean_html_to_text(item.get("description") or "")
                is_remote = item.get("remote", False)
                work_arrangement = "remote" if is_remote else "in-office"

                attributes: dict[str, Any] = {
                    "work_arrangement": work_arrangement,
                    "location": item.get("location") or "Worldwide",
                    "tech_stack": item.get("tags") or [],
                    "employment_type": ", ".join(item.get("job_types", [])) if item.get("job_types") else None,
                }

                job = JobPosting(
                    source=self.name,
                    source_job_id=slug,
                    source_url=item.get("url") or f"https://www.arbeitnow.com/jobs/{slug}",
                    title=item.get("title") or "Untitled",
                    company_name=item.get("company_name") or "Unknown Company",
                    description_text=clean_desc,
                    posted_at=pub_date,
                    attributes=attributes,
                )
                batch.append(job)

            if batch:
                inserted = await sink.save_batch(batch)
                stats["inserted"] += inserted
                stats["skipped"] += len(batch) - inserted

            if reached_cutoff or not data.get("links", {}).get("next"):
                break

            page += 1

        return stats
