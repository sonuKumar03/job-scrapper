"""RemoteOK jobs connector."""

from typing import Any
from job_scrapper.connectors.base import BaseConnector
from job_scrapper.domain.models import JobPosting
from job_scrapper.pipeline.cleaner import clean_html_to_text
from job_scrapper.pipeline.date_parser import is_within_days, parse_to_utc
from job_scrapper.storage.base import JobSink


class RemoteOKConnector(BaseConnector):
    name: str = "remoteok"
    API_URL: str = "https://remoteok.com/api"

    async def scrape(self, sink: JobSink, max_days: int = 7) -> dict[str, int]:
        stats = {"found": 0, "inserted": 0, "skipped": 0}

        response = await self.http_client.get(self.API_URL)
        if response.status_code != 200:
            return stats

        data = response.json()
        if not isinstance(data, list):
            return stats

        batch: list[JobPosting] = []

        for item in data:
            # Skip legal notices or tag summary items without 'id'
            if not isinstance(item, dict) or "id" not in item:
                continue

            stats["found"] += 1
            source_id = str(item.get("id"))

            pub_date = parse_to_utc(item.get("date"))
            if not pub_date or not is_within_days(pub_date, max_days=max_days):
                stats["skipped"] += 1
                continue

            if await sink.contains(self.name, source_id):
                stats["skipped"] += 1
                continue

            clean_desc = clean_html_to_text(item.get("description") or "")
            tags = item.get("tags") or []

            attributes: dict[str, Any] = {
                "work_arrangement": "remote",
                "location": item.get("location") or "Remote Worldwide",
                "salary_min": item.get("salary_min"),
                "salary_max": item.get("salary_max"),
                "currency": "USD" if item.get("salary_min") or item.get("salary_max") else None,
                "tech_stack": tags,
                "apply_url": item.get("apply_url"),
            }

            job = JobPosting(
                source=self.name,
                source_job_id=source_id,
                source_url=item.get("url") or f"https://remoteok.com/remote-jobs/{source_id}",
                title=item.get("position") or "Untitled",
                company_name=item.get("company") or "Unknown Company",
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
