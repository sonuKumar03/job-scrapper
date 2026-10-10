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

    async def scrape(self, sink: JobSink, max_days: int = 7) -> dict[str, Any]:
        stats = self.new_stats()

        try:
            response = await self.http_client.get(self.API_URL)
            data = response.json()
            if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
                raise ValueError("response must be a list of objects")
        except Exception as exc:
            self.record_error(stats, "feed", exc)
            return stats

        batch: list[JobPosting] = []
        unknown_dates = 0
        known_ids = await sink.contains_many(
            self.name, [str(item["id"]) for item in data if item.get("id") is not None]
        )

        for item in data:
            # Skip legal notices or tag summary items without 'id'
            if not isinstance(item, dict) or "id" not in item:
                continue

            stats["found"] += 1
            source_id = str(item.get("id"))

            pub_date = parse_to_utc(item.get("date"))
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

            try:
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
            except (ValueError, TypeError, AttributeError) as exc:
                stats["skipped"] += 1
                self.record_error(stats, f"listing {source_id}", exc)

        await self.save_jobs(sink, batch, stats)
        self.record_unknown_dates(stats, "feed", unknown_dates)

        return stats
