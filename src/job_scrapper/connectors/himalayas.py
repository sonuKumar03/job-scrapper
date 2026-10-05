"""Himalayas remote software jobs connector with high-throughput pagination."""

import asyncio
from typing import Any
from job_scrapper.connectors.base import BaseConnector
from job_scrapper.domain.models import JobPosting
from job_scrapper.pipeline.cleaner import clean_html_to_text
from job_scrapper.pipeline.date_parser import is_within_days, parse_to_utc
from job_scrapper.storage.base import JobSink


class HimalayasConnector(BaseConnector):
    name: str = "himalayas"
    API_URL: str = "https://himalayas.app/jobs/api"
    PAGE_SIZE: int = 20  # Himalayas enforces 20 items per page

    async def _fetch_page(self, offset: int) -> list[dict[str, Any]]:
        url = f"{self.API_URL}?limit={self.PAGE_SIZE}&offset={offset}"
        try:
            resp = await self.http_client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("jobs", [])
        except Exception:
            pass
        return []

    async def scrape(self, sink: JobSink, max_days: int = 90) -> dict[str, int]:
        stats = {"found": 0, "inserted": 0, "skipped": 0}
        offset = 0
        concurrency = 3
        chunk_step = self.PAGE_SIZE * concurrency
        max_total_jobs = 12000  # Cap per scrape execution

        while offset < max_total_jobs:
            # Fetch a chunk of pages concurrently
            tasks = [self._fetch_page(offset + (i * self.PAGE_SIZE)) for i in range(concurrency)]
            results = await asyncio.gather(*tasks)

            chunk_jobs: list[dict[str, Any]] = []
            for page_jobs in results:
                chunk_jobs.extend(page_jobs)

            if not chunk_jobs:
                break

            batch: list[JobPosting] = []
            reached_cutoff = False

            for item in chunk_jobs:
                stats["found"] += 1
                source_id = str(item.get("guid") or item.get("applicationLink") or "")

                pub_date = parse_to_utc(item.get("pubDate"))
                if not pub_date:
                    stats["skipped"] += 1
                    continue

                if not is_within_days(pub_date, max_days=max_days):
                    stats["skipped"] += 1
                    reached_cutoff = True
                    continue

                if source_id and await sink.contains(self.name, source_id):
                    stats["skipped"] += 1
                    continue

                clean_desc = clean_html_to_text(item.get("description") or item.get("excerpt") or "")
                location_list = item.get("locationRestrictions") or []
                location_str = ", ".join(location_list) if isinstance(location_list, list) else str(location_list)
                categories = item.get("categories") or []

                attributes: dict[str, Any] = {
                    "seniority": item.get("seniority"),
                    "work_arrangement": "remote",
                    "location": location_str or "Remote Worldwide",
                    "salary_min": item.get("minSalary"),
                    "salary_max": item.get("maxSalary"),
                    "currency": item.get("currency"),
                    "tech_stack": categories,
                    "employment_type": item.get("employmentType"),
                }

                job = JobPosting(
                    source=self.name,
                    source_job_id=source_id,
                    source_url=item.get("applicationLink") or f"https://himalayas.app/companies/{item.get('companySlug')}",
                    title=item.get("title") or "Untitled",
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

            if reached_cutoff or len(chunk_jobs) < chunk_step:
                break

            offset += chunk_step

        return stats
