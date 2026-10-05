"""Himalayas remote software jobs connector with high-throughput pagination."""

from typing import Any
from urllib.parse import urlencode
from job_scrapper.connectors.base import BaseConnector
from job_scrapper.domain.models import JobPosting
from job_scrapper.pipeline.cleaner import clean_html_to_text
from job_scrapper.pipeline.date_parser import is_within_days, parse_to_utc
from job_scrapper.storage.base import JobSink


class HimalayasConnector(BaseConnector):
    name: str = "himalayas"
    API_URL: str = "https://himalayas.app/jobs/api"
    PAGE_SIZE: int = 20
    MAX_PAGES: int = 500

    async def _fetch_page(
        self, cursor: str | None, page_number: int, stats: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], str | None, int] | None:
        params = {"limit": self.PAGE_SIZE}
        if cursor is not None:
            params["cursor"] = cursor
        url = f"{self.API_URL}?{urlencode(params)}"
        try:
            resp = await self.http_client.get(url)
            data = resp.json()
            if (
                not isinstance(data, dict)
                or not isinstance(data.get("jobs"), list)
                or not isinstance(data.get("totalCount"), int)
                or any(not isinstance(item, dict) for item in data["jobs"])
            ):
                raise ValueError("response jobs must be a list")
            next_cursor = data.get("nextCursor")
            if next_cursor is not None and (not isinstance(next_cursor, str) or not next_cursor):
                raise ValueError("nextCursor must be a non-empty string")
            return data["jobs"], next_cursor, data["totalCount"]
        except Exception as exc:
            self.record_error(stats, f"page {page_number}", exc)
            return None

    async def scrape(self, sink: JobSink, max_days: int = 7) -> dict[str, Any]:
        stats = self.new_stats()
        cursor: str | None = None
        seen_cursors: set[str] = set()
        unknown_dates = 0
        total_count: int | None = None
        scanned_count = 0
        for page in range(self.MAX_PAGES):
            if cursor is not None:
                if cursor in seen_cursors:
                    self.record_error(stats, f"page {page + 1}", ValueError("repeated cursor"))
                    break
                seen_cursors.add(cursor)
            result = await self._fetch_page(cursor, page + 1, stats)
            if result is None:
                break
            page_jobs, next_cursor, page_total = result
            if total_count is None:
                total_count = page_total
            scanned_count += len(page_jobs)
            batch: list[JobPosting] = []
            for item in page_jobs:
                stats["found"] += 1
                source_id = str(item.get("guid") or item.get("applicationLink") or "")

                pub_date = parse_to_utc(item.get("pubDate"))
                if not pub_date:
                    unknown_dates += 1
                    stats["skipped"] += 1
                    continue

                if not is_within_days(pub_date, max_days=max_days):
                    stats["skipped"] += 1
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

            if next_cursor is None:
                if total_count is not None and scanned_count < total_count:
                    self.record_error(stats, f"page {page + 1}", ValueError("cursor ended before totalCount"))
                break
            cursor = next_cursor
        else:
            stats["truncated"] = True
            stats["errors"].append(f"page safety limit reached ({self.MAX_PAGES} pages)")

        self.record_unknown_dates(stats, "feed", unknown_dates)

        return stats
