"""Lever ATS direct employer board connector."""

import asyncio
from typing import Any
from job_scrapper.connectors.base import BaseConnector
from job_scrapper.connectors.company_sources import load_company_sources
from job_scrapper.domain.models import JobPosting
from job_scrapper.pipeline.cleaner import clean_html_to_text
from job_scrapper.pipeline.date_parser import parse_to_utc
from job_scrapper.storage.base import JobSink

DEFAULT_LEVER_COMPANIES = [
    "palantir",
    "spotify",
    "sysdig",
    "brightedge",
    "brilliant",
    "360learning",
    "parallelwireless",
    "lever",
    "paralleldomain",
    "kepler",
    "scanifly",
    "lyrahealth",
    "ekimetrics",
    "lwolf",
]


class LeverConnector(BaseConnector):
    name: str = "lever"
    BASE_URL: str = "https://api.lever.co/v0/postings"
    PAGE_SIZE: int = 100
    MAX_PAGES: int = 500

    def __init__(self, companies: list[str] | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        sources = [
            source for source in load_company_sources(self.name)
            if source.status == "supported" and source.account_key
        ]
        self.company_names = {source.account_key: source.company_name for source in sources}
        defaults = list(dict.fromkeys([*DEFAULT_LEVER_COMPANIES, *self.company_names]))
        self.companies = companies if companies is not None else defaults

    async def scrape(self, sink: JobSink, max_days: int = 7) -> dict[str, Any]:
        stats = self.new_stats()

        async def scrape_company(company: str) -> None:
            account_stats = self.new_stats()
            skip = 0
            try:
                for page in range(self.MAX_PAGES):
                    if self.stop_requested:
                        break
                    url = f"{self.BASE_URL}/{company}?mode=json&skip={skip}&limit={self.PAGE_SIZE}"
                    try:
                        response = await self.http_client.get(url)
                        raw_jobs = response.json()
                        if not isinstance(raw_jobs, list) or any(not isinstance(item, dict) for item in raw_jobs):
                            raise ValueError("response must be a list of objects")
                    except Exception as exc:
                        self.record_error(account_stats, f"page {page + 1}", exc)
                        break
                    if not raw_jobs:
                        break

                    ids = [str(item["id"]) for item in raw_jobs if item.get("id") is not None]
                    stored_ids = await sink.contains_many(self.name, [f"{company}:{source_id}" for source_id in ids])

                    batch: list[JobPosting] = []
                    unknown_dates = 0
                    for item in raw_jobs:
                        account_stats["found"] += 1
                        raw_id = item.get("id")
                        if raw_id is None:
                            account_stats["skipped"] += 1
                            account_stats["errors"].append("listing missing id")
                            account_stats["truncated"] = True
                            continue
                        raw_id = str(raw_id)
                        source_id = f"{company}:{raw_id}"
                        pub_date = parse_to_utc(item.get("createdAt"))
                        if not pub_date:
                            unknown_dates += 1
                            account_stats["skipped"] += 1
                            continue
                        if source_id in stored_ids:
                            account_stats["skipped"] += 1
                            continue

                        try:
                            parts = [item.get("descriptionPlain") or clean_html_to_text(item.get("description") or "")]
                            for section in item.get("lists") or []:
                                if isinstance(section, dict):
                                    parts.extend([
                                        section.get("text") or "",
                                        clean_html_to_text(section.get("content") or ""),
                                    ])
                            parts.append(item.get("additionalPlain") or clean_html_to_text(item.get("additional") or ""))
                            raw_desc = "\n\n".join(part.strip() for part in parts if isinstance(part, str) and part.strip())
                            if not isinstance(raw_desc, str) or not raw_desc.strip():
                                raise ValueError("listing missing description")
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

                            job = JobPosting(
                                source=self.name,
                                source_job_id=source_id,
                                source_url=item.get("hostedUrl") or item.get("applyUrl") or f"https://jobs.lever.co/{company}/{raw_id}",
                                title=item.get("text") or "Untitled",
                                company_name=self.company_names.get(company, company.capitalize()),
                                description_text=raw_desc,
                                posted_at=pub_date,
                                attributes={
                                    "work_arrangement": work_arrangement,
                                    "location": location_str,
                                    "team": team,
                                    "employment_type": commitment,
                                    "company_slug": company,
                                },
                            )
                            batch.append(job)
                        except Exception as exc:
                            account_stats["skipped"] += 1
                            self.record_error(account_stats, f"job {raw_id}", exc)

                    await self.save_jobs(sink, batch, account_stats)
                    self.record_unknown_dates(account_stats, f"page {page + 1}", unknown_dates)
                    if len(raw_jobs) < self.PAGE_SIZE:
                        break
                    skip += len(raw_jobs)
                else:
                    account_stats["truncated"] = True
                    account_stats["errors"].append(f"page safety limit reached ({self.MAX_PAGES} pages)")
            except Exception as exc:
                self.record_error(account_stats, "processing", exc)
            finally:
                self.record_account_stats(stats, company, account_stats)

        for start in range(0, len(self.companies), 3):
            if self.stop_requested:
                break
            companies = self.companies[start:start + 3]
            results = await asyncio.gather(
                *(scrape_company(company) for company in companies), return_exceptions=True
            )
            for company, result in zip(companies, results):
                if isinstance(result, Exception):
                    self.record_error(stats, f"company {company}", result)
        return stats
