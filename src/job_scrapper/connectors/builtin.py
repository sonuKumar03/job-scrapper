"""Built In job listings scraped from public HTML and JobPosting metadata."""

import asyncio
import json
from typing import Any
from urllib.parse import parse_qs, urljoin, urlsplit

from selectolax.lexbor import LexborHTMLParser

from job_scrapper.connectors.base import BaseConnector
from job_scrapper.domain.models import JobPosting
from job_scrapper.pipeline.cleaner import clean_html_to_text
from job_scrapper.pipeline.date_parser import is_within_days, parse_to_utc
from job_scrapper.storage.base import JobSink


class BuiltInConnector(BaseConnector):
    name = "builtin"
    BASE_URL = "https://builtin.com"
    MAX_PAGES = 500

    async def _fetch_job(self, source_id: str, url: str, max_days: int,
                         stats: dict[str, Any]) -> JobPosting | None:
        try:
            response = await self.http_client.get(url)
            page = LexborHTMLParser(response.text)
            metadata = next(
                json.loads(script.text())
                for script in page.css('script[type="application/ld+json"]')
                if "JobPosting" in script.text()
            )
            graphs = metadata.get("@graph", [metadata])
            item = next(job for job in graphs if job.get("@type") == "JobPosting")
            if not isinstance(item, dict):
                raise ValueError("JobPosting metadata must be an object")
        except Exception as exc:
            self.record_error(stats, f"job {source_id}", exc)
            return None

        posted_at = parse_to_utc(item.get("datePosted"))
        if not posted_at:
            self.record_unknown_dates(stats, f"job {source_id}", 1)
            stats["skipped"] += 1
            return None
        if not is_within_days(posted_at, max_days=max_days):
            stats["skipped"] += 1
            return None

        organization = item.get("hiringOrganization") or {}
        company = organization.get("name") if isinstance(organization, dict) else None
        description = clean_html_to_text(item.get("description") or "")
        if not all(isinstance(value, str) and value.strip() for value in
                   (item.get("title"), company, description)):
            self.record_error(stats, f"job {source_id}", ValueError("missing title, company, or description"))
            stats["skipped"] += 1
            return None

        locations = item.get("jobLocation") or []
        if isinstance(locations, dict):
            locations = [locations]
        place_names = []
        if isinstance(locations, list):
            for place in locations:
                address = place.get("address") if isinstance(place, dict) else None
                if isinstance(address, dict):
                    name = ", ".join(str(address[key]) for key in
                                     ("addressLocality", "addressRegion", "addressCountry")
                                     if address.get(key))
                    if name:
                        place_names.append(name)
        arrangement = "remote" if item.get("jobLocationType") == "TELECOMMUTE" else "unknown"
        salary = item.get("baseSalary") or {}
        salary_value = salary.get("value") if isinstance(salary, dict) else None
        salary_value = salary_value if isinstance(salary_value, dict) else {}

        return JobPosting(
            source=self.name,
            source_job_id=source_id,
            source_url=url,
            title=item["title"],
            company_name=company,
            description_text=description,
            posted_at=posted_at,
            attributes={
                "work_arrangement": arrangement,
                "location": "; ".join(place_names) or None,
                "employment_type": item.get("employmentType"),
                "salary_min": salary_value.get("minValue"),
                "salary_max": salary_value.get("maxValue"),
                "currency": salary.get("currency") if isinstance(salary, dict) else None,
            },
        )

    async def scrape(self, sink: JobSink, max_days: int = 7) -> dict[str, Any]:
        stats = self.new_stats()
        seen_ids: set[str] = set()

        for page_number in range(1, self.MAX_PAGES + 1):
            url = f"{self.BASE_URL}/jobs?daysSinceUpdated={max_days}&page={page_number}"
            try:
                response = await self.http_client.get(url)
                page = LexborHTMLParser(response.text)
                links = []
                for anchor in page.css('a[href^="/job/"]'):
                    href = anchor.attributes.get("href", "")
                    source_id = urlsplit(href).path.rsplit("/", 1)[-1]
                    if source_id.isdigit() and source_id not in seen_ids:
                        links.append((source_id, urljoin(self.BASE_URL, href)))
                        seen_ids.add(source_id)
                if not links and page_number == 1:
                    raise ValueError("no job links on first listing page")
            except Exception as exc:
                self.record_error(stats, f"page {page_number}", exc)
                break

            stats["found"] += len(links)
            known_ids = await sink.contains_many(self.name, [source_id for source_id, _ in links])
            new_links = [(source_id, job_url) for source_id, job_url in links
                         if source_id not in known_ids]
            stats["skipped"] += len(links) - len(new_links)
            jobs = await asyncio.gather(*(
                self._fetch_job(source_id, job_url, max_days, stats)
                for source_id, job_url in new_links
            ))
            await self.save_jobs(sink, [job for job in jobs if job is not None], stats)

            has_next = any(
                parse_qs(urlsplit(anchor.attributes.get("href", "")).query).get("page") == [str(page_number + 1)]
                for anchor in page.css("a[href]")
            )
            if not has_next:
                break
        else:
            stats["truncated"] = True
            stats["errors"].append(f"page safety limit reached ({self.MAX_PAGES} pages)")

        return stats
