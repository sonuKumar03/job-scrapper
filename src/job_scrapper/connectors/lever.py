"""Lever ATS direct employer board connector."""

from typing import Any
from job_scrapper.connectors.base import BaseConnector
from job_scrapper.domain.models import JobPosting
from job_scrapper.pipeline.cleaner import clean_html_to_text
from job_scrapper.pipeline.date_parser import is_within_days, parse_to_utc
from job_scrapper.storage.base import JobSink

DEFAULT_LEVER_COMPANIES = [
    "palantir",
    "spotify",
    "atlassian",
    "postman",
    "sourcegraph",
    "benchling",
    "coursera",
    "lever",
    "fullstory",
    "mux",
    "brex",
    "dbt",
    "temporal",
    "launchdarkly",
]


class LeverConnector(BaseConnector):
    name: str = "lever"
    BASE_URL: str = "https://api.lever.co/v0/postings"
    PAGE_SIZE: int = 100
    MAX_PAGES: int = 500

    def __init__(self, companies: list[str] | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.companies = companies or DEFAULT_LEVER_COMPANIES

    async def scrape(self, sink: JobSink, max_days: int = 7) -> dict[str, Any]:
        stats = self.new_stats()

        for company in self.companies:
            skip = 0
            for page in range(self.MAX_PAGES):
                url = f"{self.BASE_URL}/{company}?mode=json&skip={skip}&limit={self.PAGE_SIZE}"
                try:
                    response = await self.http_client.get(url)
                    raw_jobs = response.json()
                    if not isinstance(raw_jobs, list) or any(not isinstance(item, dict) for item in raw_jobs):
                        raise ValueError("response must be a list of objects")
                except Exception as exc:
                    self.record_error(stats, f"company {company} page {page + 1}", exc)
                    break
                if not raw_jobs:
                    break

                batch: list[JobPosting] = []
                unknown_dates = 0
                for item in raw_jobs:
                    stats["found"] += 1
                    source_id = str(item.get("id"))
                    pub_date = parse_to_utc(item.get("createdAt"))
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

                    raw_desc = item.get("descriptionPlain") or clean_html_to_text(item.get("description") or "")
                    categories = item.get("categories") or {}
                    location_str = categories.get("location") or "Worldwide"
                    team = categories.get("team")
                    commitment = categories.get("commitment")
                    work_type = (item.get("workplaceType") or "unknown").lower()
                    if "remote" in work_type:
                        work_arrangement = "remote"
                    elif "hybrid" in work_type:
                        work_arrangement = "hybrid"
                    elif "site" in work_type or "office" in work_type:
                        work_arrangement = "in-office"
                    else:
                        work_arrangement = "unknown"

                    attributes: dict[str, Any] = {
                        "work_arrangement": work_arrangement,
                        "location": location_str,
                        "team": team,
                        "employment_type": commitment,
                        "company_slug": company,
                    }
                    job = JobPosting(
                        source=self.name,
                        source_job_id=source_id,
                        source_url=item.get("hostedUrl") or item.get("applyUrl") or f"https://jobs.lever.co/{company}/{source_id}",
                        title=item.get("text") or "Untitled",
                        company_name=company.capitalize(),
                        description_text=raw_desc,
                        posted_at=pub_date,
                        attributes=attributes,
                    )
                    batch.append(job)

                if batch:
                    inserted = await sink.save_batch(batch)
                    stats["inserted"] += inserted
                    stats["skipped"] += len(batch) - inserted
                self.record_unknown_dates(stats, f"company {company} page {page + 1}", unknown_dates)
                if len(raw_jobs) < self.PAGE_SIZE:
                    break
                skip += len(raw_jobs)
            else:
                stats["truncated"] = True
                stats["errors"].append(f"company {company}: page safety limit reached ({self.MAX_PAGES} pages)")

        return stats
