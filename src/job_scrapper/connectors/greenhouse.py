"""Greenhouse ATS direct employer board connector."""

import asyncio
import html
from typing import Any
from job_scrapper.connectors.base import BaseConnector
from job_scrapper.companies.contracts import CompanyTarget, validate_targets
from job_scrapper.domain.models import JobPosting
from job_scrapper.pipeline.cleaner import clean_html_to_text
from job_scrapper.pipeline.date_parser import is_within_days, parse_to_utc
from job_scrapper.storage.base import JobSink

class GreenhouseConnector(BaseConnector):
    name: str = "greenhouse"
    BASE_URL: str = "https://boards-api.greenhouse.io/v1/boards"

    def __init__(self, targets: tuple[CompanyTarget, ...], **kwargs: Any) -> None:
        validate_targets(targets, self.name)
        super().__init__(**kwargs)
        self.company_names = {target.account_key: target.company_name for target in targets}
        self.companies = list(self.company_names)

    async def scrape(self, sink: JobSink, max_days: int = 7) -> dict[str, Any]:
        stats = self.new_stats()

        async def scrape_company(company: str) -> None:
            account_stats = self.new_stats()
            unknown_dates = 0
            url = f"{self.BASE_URL}/{company}/jobs?content=true"
            try:
                response = await self.http_client.get(url)
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError("response must be an object")
                raw_jobs = data.get("jobs")
                if not isinstance(raw_jobs, list) or any(not isinstance(item, dict) for item in raw_jobs):
                    raise ValueError("response jobs must be a list of objects")
            except Exception as exc:
                self.record_error(account_stats, "listing", exc)
                self.record_account_stats(stats, company, account_stats)
                return

            try:
                batch: list[JobPosting] = []
                ids = [str(item["id"]) for item in raw_jobs if item.get("id") is not None]
                stored_ids = await sink.contains_many(self.name, [f"{company}:{source_id}" for source_id in ids])

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

                    pub_date = parse_to_utc(item.get("first_published"))
                    if not pub_date:
                        unknown_dates += 1
                        account_stats["skipped"] += 1
                        continue
                    if not is_within_days(pub_date, max_days):
                        account_stats["skipped"] += 1
                        continue
                    if source_id in stored_ids:
                        account_stats["skipped"] += 1
                        continue

                    try:
                        clean_desc = clean_html_to_text(html.unescape(item.get("content") or ""))
                        if not clean_desc:
                            raise ValueError("listing missing description")
                        location_dict = item.get("location") or {}
                        location_str = location_dict.get("name") if isinstance(location_dict, dict) else str(location_dict)
                        loc_lower = (location_str or "").lower()
                        work_arrangement = (
                            "remote" if "remote" in loc_lower else
                            "hybrid" if "hybrid" in loc_lower else
                            "in-office" if loc_lower else "unknown"
                        )
                        departments = item.get("departments") or []
                        depts = [d.get("name") for d in departments if isinstance(d, dict) and d.get("name")]
                        job = JobPosting(
                            source=self.name,
                            source_job_id=source_id,
                            source_url=item.get("absolute_url") or f"https://boards.greenhouse.io/{company}/jobs/{raw_id}",
                            title=item.get("title") or "Untitled",
                            company_name=item.get("company_name") or self.company_names.get(company) or company.capitalize(),
                            description_text=clean_desc,
                            posted_at=pub_date,
                            attributes={
                                "work_arrangement": work_arrangement,
                                "location": location_str,
                                "departments": depts,
                                "company_slug": company,
                            },
                        )
                        batch.append(job)
                    except Exception as exc:
                        account_stats["skipped"] += 1
                        self.record_error(account_stats, f"job {raw_id}", exc)

                await self.save_jobs(sink, batch, account_stats)
                self.record_unknown_dates(account_stats, "listing", unknown_dates)
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
