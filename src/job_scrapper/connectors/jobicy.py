"""Jobicy remote jobs connector with cursor pagination."""

from typing import Any
from urllib.parse import urlencode
from job_scrapper.connectors.base import BaseConnector
from job_scrapper.domain.models import JobPosting
from job_scrapper.pipeline.cleaner import clean_html_to_text
from job_scrapper.pipeline.date_parser import is_within_days, parse_to_utc
from job_scrapper.storage.base import JobSink


class JobicyConnector(BaseConnector):
    name: str = "jobicy"
    API_URL: str = "https://jobicy.com/api/v2/remote-jobs"
    PAGE_SIZE: int = 200
    MAX_PAGES: int = 500

    async def scrape(self, sink: JobSink, max_days: int = 7) -> dict[str, Any]:
        stats = self.new_stats()
        stats.update(dict.fromkeys(self.DIAGNOSTIC_COUNTS, 0))
        cursor: str | None = None
        seen_cursors: set[str] = set()
        unknown_dates = 0

        if max_days > 7:
            stats["truncated"] = True
            stats['warnings'] = ['Jobicy only exposes postings from the last 7 days; requested history is incomplete']
            stats['coverage'] = {'requested_days': max_days, 'available_days': 7}

        for page in range(self.MAX_PAGES):
            if self.stop_requested:
                break
            if cursor is not None:
                if cursor in seen_cursors:
                    self.record_error(stats, f"page {page + 1}", ValueError("repeated cursor"))
                    break
                seen_cursors.add(cursor)
            params: dict[str, str | int] = {"count": self.PAGE_SIZE}
            if cursor is not None:
                params["cursor"] = cursor
            try:
                response = await self.http_client.get(f"{self.API_URL}?{urlencode(params)}")
                data = response.json()
                if (
                    not isinstance(data, dict)
                    or not isinstance(data.get("jobs"), list)
                    or any(not isinstance(item, dict) for item in data["jobs"])
                    or data.get("success") is False
                    or not isinstance(data.get("hasMore"), bool)
                    or (data.get("nextCursor") is not None and (not isinstance(data["nextCursor"], str) or not data["nextCursor"]))
                    or bool(data.get("nextCursor")) != data["hasMore"]
                ):
                    raise ValueError("response jobs or nextCursor have invalid types")
            except Exception as exc:
                self.record_error(stats, f"page {page + 1}", exc)
                break

            raw_jobs = data["jobs"]
            stats['listing_pages'] += 1
            known_ids = await sink.contains_many(
                self.name, [str(item["id"]) for item in raw_jobs if item.get("id") is not None]
            )
            batch: list[JobPosting] = []
            for item in raw_jobs:
                stats["found"] += 1
                source_id = str(item.get("id") or "")
                pub_date = parse_to_utc(item.get("pubDate"))
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
                    stats['detail_attempted'] += 1
                    raw_desc = item.get("jobDescription") or item.get("jobExcerpt") or ""
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
                    batch.append(JobPosting(
                        source=self.name,
                        source_job_id=source_id,
                        source_url=item.get("url") or "",
                        title=item.get("jobTitle") or "",
                        company_name=item.get("companyName") or "",
                        description_text=clean_html_to_text(raw_desc),
                        posted_at=pub_date,
                        attributes=attributes,
                    ))
                    stats['detail_valid'] += 1
                except (ValueError, TypeError, AttributeError) as exc:
                    stats['detail_invalid'] += 1
                    stats["skipped"] += 1
                    self.record_error(stats, f"listing {source_id}", exc)

            await self.save_jobs(sink, batch, stats)
            cursor = data.get("nextCursor")
            if cursor is None:
                break
        else:
            stats["truncated"] = True
            stats["errors"].append(f"page safety limit reached ({self.MAX_PAGES} pages)")

        self.record_unknown_dates(stats, "feed", unknown_dates)
        return stats
