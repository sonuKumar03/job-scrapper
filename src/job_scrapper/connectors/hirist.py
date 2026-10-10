"""Hirist's public category and job detail APIs."""

import asyncio
from typing import Any

from job_scrapper.connectors.base import BaseConnector
from job_scrapper.domain.models import JobPosting
from job_scrapper.pipeline.cleaner import clean_html_to_text
from job_scrapper.pipeline.date_parser import is_within_days, parse_to_utc
from job_scrapper.storage.base import JobSink


class HiristConnector(BaseConnector):
    name = "hirist"
    BASE_URL = "https://gladiator.hirist.tech/job"
    CATEGORY_IDS = range(1, 16)
    PAGE_SIZE = 500
    MAX_PAGES = 100

    async def _fetch_job(self, listing: dict[str, Any], posted_at: Any,
                         stats: dict[str, Any]) -> JobPosting | None:
        if self.stop_requested:
            return None
        source_id = str(listing["id"])
        try:
            response = await self.http_client.get(f"{self.BASE_URL}/detail?jobcode={source_id}")
            item = response.json()["data"]
            if not isinstance(item, dict) or item.get("id") != listing["id"]:
                raise ValueError("invalid job detail response")
            company_data = item.get("companyData") or {}
            company = company_data.get("companyName") if isinstance(company_data, dict) else None
            description = clean_html_to_text(item.get("introText") or "")
            if not all(isinstance(value, str) and value.strip() for value in
                       (item.get("title"), company, description, item.get("jobDetailUrl"))):
                raise ValueError("missing title, company, description, or URL")
            locations = item.get("locations") or []
            return JobPosting(
                source=self.name,
                source_job_id=source_id,
                source_url=item["jobDetailUrl"],
                title=item["title"].strip(),
                company_name=company,
                description_text=description,
                posted_at=posted_at,
                attributes={
                    "location": ", ".join(place["name"] for place in locations
                                          if isinstance(place, dict) and place.get("name")) or None,
                    "tech_stack": [tag["name"] for tag in item.get("tags", [])
                                   if isinstance(tag, dict) and tag.get("name")],
                    "experience_years_min": item.get("min"),
                    "experience_years_max": item.get("max"),
                    "work_arrangement": "remote" if item.get("workFromHome") else "unknown",
                },
            )
        except Exception as exc:
            self.record_error(stats, f"job {source_id}", exc)
            stats["skipped"] += 1
            return None

    async def scrape(self, sink: JobSink, max_days: int = 7) -> dict[str, Any]:
        stats = self.new_stats()
        seen_ids: set[str] = set()
        for category_id in self.CATEGORY_IDS:
            if self.stop_requested:
                break
            for page_number in range(self.MAX_PAGES):
                if self.stop_requested:
                    break
                try:
                    response = await self.http_client.get(
                        f"{self.BASE_URL}/category/?page={page_number}&industry=&categoryId={category_id}&size={self.PAGE_SIZE}"
                    )
                    data = response.json()
                    listings = data.get("data")
                    if not isinstance(listings, list):
                        raise ValueError("invalid category response")
                    fresh = [job for job in listings if isinstance(job, dict)
                             and isinstance(job.get("id"), int)
                             and str(job["id"]) not in seen_ids]
                    seen_ids.update(str(job["id"]) for job in fresh)
                except Exception as exc:
                    self.record_error(stats, f"category {category_id} page {page_number + 1}", exc)
                    break

                stats["found"] += len(fresh)
                known_ids = await sink.contains_many(self.name, [str(job["id"]) for job in fresh])
                recent = []
                for listing in fresh:
                    if str(listing["id"]) in known_ids:
                        stats["skipped"] += 1
                        continue
                    posted_at = parse_to_utc(listing.get("createdTimeMs"))
                    if posted_at is None:
                        self.record_unknown_dates(stats, f"job {listing['id']}", 1)
                        stats["skipped"] += 1
                    elif is_within_days(posted_at, max_days):
                        recent.append((listing, posted_at))
                    else:
                        stats["skipped"] += 1
                batch: list[JobPosting] = []
                for start in range(0, len(recent), 3):
                    if self.stop_requested:
                        break
                    jobs = await asyncio.gather(*(self._fetch_job(job, posted_at, stats)
                                                  for job, posted_at in recent[start:start + 3]))
                    batch.extend(job for job in jobs if job is not None)
                await self.save_jobs(sink, batch, stats)
                if not data.get("hasMore"):
                    break
            else:
                stats["truncated"] = True
                stats["errors"].append(f"category {category_id} page safety limit reached")
        return stats
