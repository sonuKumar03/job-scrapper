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

    async def scrape(self, sink: JobSink, max_days: int = 7) -> dict[str, Any]:
        stats = self.new_stats()
        page = 1
        max_pages = 50  # Up to 50 pages (~5,000+ jobs)

        while page <= max_pages:
            if self.stop_requested:
                break
            url = f"{self.API_URL}?page={page}"
            try:
                response = await self.http_client.get(url)
                data = response.json()
                if (
                    not isinstance(data, dict)
                    or not isinstance(data.get("data"), list)
                    or any(not isinstance(item, dict) for item in data["data"])
                ):
                    raise ValueError("response data must be a list of objects")
            except Exception as exc:
                self.record_error(stats, f"page {page}", exc)
                break
            items = data["data"]
            links = data.get("links") or {}
            if not isinstance(links, dict):
                self.record_error(stats, f"page {page}", ValueError("links must be an object"))
                break
            if not items:
                if links.get("next"):
                    self.record_error(stats, f"page {page}", ValueError("empty page has a next link"))
                break

            known_ids = await sink.contains_many(
                self.name, [str(item["slug"]) for item in items if item.get("slug")]
            )

            batch: list[JobPosting] = []
            unknown_dates = 0

            for item in items:
                stats["found"] += 1
                slug = item.get("slug")
                if not slug:
                    stats["skipped"] += 1
                    continue

                created_at = item.get("created_at")
                pub_date = parse_to_utc(created_at)
                if not pub_date:
                    unknown_dates += 1
                    stats["skipped"] += 1
                    continue

                if not is_within_days(pub_date, max_days=max_days):
                    stats["skipped"] += 1
                    continue

                if slug in known_ids:
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

            await self.save_jobs(sink, batch, stats)
            self.record_unknown_dates(stats, f"page {page}", unknown_dates)

            if not links.get("next"):
                break

            page += 1
        else:
            stats["truncated"] = True
            stats["errors"].append(f"page safety limit reached ({max_pages} pages)")

        return stats
