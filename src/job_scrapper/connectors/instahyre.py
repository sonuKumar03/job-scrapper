"""Instahyre's public job search API and public job pages."""

import asyncio
from typing import Any

from selectolax.lexbor import LexborHTMLParser

from job_scrapper.connectors.base import BaseConnector
from job_scrapper.domain.models import JobPosting
from job_scrapper.pipeline.cleaner import clean_html_to_text
from job_scrapper.pipeline.date_parser import is_within_days, parse_to_utc
from job_scrapper.pipeline.job_metadata import parse_job_metadata
from job_scrapper.storage.base import JobSink


class InstahyreConnector(BaseConnector):
    name = "instahyre"
    SEARCH_URL = "https://www.instahyre.com/api/v1/job_search"
    MAX_PAGES = 1000

    async def _fetch_job(self, listing: dict[str, Any], max_days: int,
                         stats: dict[str, Any]) -> JobPosting | None:
        source_id = str(listing["id"])
        try:
            url = listing["public_url"]
            response = await self.http_client.get(url)
            page = LexborHTMLParser(response.text)
            item = parse_job_metadata(script.text() for script in page.css('script[type="application/ld+json"]'))
            posted_at = parse_to_utc(item.get("datePosted"))
            if posted_at is None:
                self.record_unknown_dates(stats, f"job {source_id}", 1)
                stats["skipped"] += 1
                return None
            if not is_within_days(posted_at, max_days):
                stats["skipped"] += 1
                return None
            organization = item.get("hiringOrganization") or {}
            company = organization.get("name") if isinstance(organization, dict) else None
            description = clean_html_to_text(item.get("description") or "")
            if not all(isinstance(value, str) and value.strip() for value in
                       (item.get("title"), company, description)):
                raise ValueError("missing title, company, or description")
            return JobPosting(
                source=self.name,
                source_job_id=source_id,
                source_url=url,
                title=item["title"],
                company_name=company,
                description_text=description,
                posted_at=posted_at,
                attributes={
                    "location": listing.get("locations"),
                    "tech_stack": listing.get("keywords") or [],
                    "employment_type": item.get("employmentType"),
                    "work_arrangement": "remote" if listing.get("locations") == "Work From Home" else "unknown",
                },
            )
        except Exception as exc:
            self.record_error(stats, f"job {source_id}", exc)
            stats["skipped"] += 1
            return None

    async def scrape(self, sink: JobSink, max_days: int = 7) -> dict[str, Any]:
        stats = self.new_stats()
        seen_ids: set[str] = set()
        for page_number in range(self.MAX_PAGES):
            if self.stop_requested:
                break
            try:
                response = await self.http_client.get(
                    f"{self.SEARCH_URL}?company_size=0&isLandingPage=true&job_type=0&offset={page_number * 20}"
                )
                data = response.json()
                listings = data.get("objects")
                meta = data.get("meta")
                if not isinstance(listings, list) or not isinstance(meta, dict):
                    raise ValueError("invalid job search response")
                if page_number == 0 and not listings:
                    raise ValueError("no jobs on first listing page")
                fresh = [job for job in listings if isinstance(job, dict)
                         and isinstance(job.get("id"), int)
                         and isinstance(job.get("public_url"), str)
                         and str(job["id"]) not in seen_ids]
                seen_ids.update(str(job["id"]) for job in fresh)
            except Exception as exc:
                self.record_error(stats, f"page {page_number + 1}", exc)
                break

            stats["found"] += len(fresh)
            known_ids = await sink.contains_many(self.name, [str(job["id"]) for job in fresh])
            new_listings = [job for job in fresh if str(job["id"]) not in known_ids]
            stats["skipped"] += len(fresh) - len(new_listings)
            jobs = await asyncio.gather(*(self._fetch_job(job, max_days, stats) for job in new_listings))
            await self.save_jobs(sink, [job for job in jobs if job is not None], stats)
            if not meta.get("next"):
                break
        else:
            stats["truncated"] = True
            stats["errors"].append(f"page safety limit reached ({self.MAX_PAGES} pages)")
        return stats
