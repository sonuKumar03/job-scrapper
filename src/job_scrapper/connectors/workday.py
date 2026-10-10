"""Public Workday CXS job search connector."""

import asyncio
from typing import Any
from urllib.parse import urlsplit

from job_scrapper.connectors.base import BaseConnector
from job_scrapper.companies.contracts import CompanyTarget, validate_targets
from job_scrapper.domain.models import JobPosting
from job_scrapper.pipeline.cleaner import clean_html_to_text
from job_scrapper.pipeline.date_parser import is_within_days, parse_to_utc
from job_scrapper.storage.base import JobSink


class WorkdayConnector(BaseConnector):
    name = "workday"
    PAGE_SIZE = 20
    MAX_PAGES = 500

    def __init__(self, targets: tuple[CompanyTarget, ...], **kwargs: Any) -> None:
        validate_targets(targets, self.name)
        super().__init__(**kwargs)
        self.companies = {target.account_key: target.company_name for target in targets}
        self.source_urls = {target.account_key: target.board_url for target in targets}

    async def scrape(self, sink: JobSink, max_days: int = 7) -> dict[str, Any]:
        stats = self.new_stats()
        detail_limit = asyncio.Semaphore(3)

        async def scrape_company(account: str, name: str) -> None:
            row = self.new_stats()
            try:
                host = urlsplit(self.source_urls[account]).netloc
                tenant, site = account.split(":", 1)
                base_url = f"https://{host}/wday/cxs/{tenant}/{site}"
                offset = 0
                cap_reported = False
                for page in range(self.MAX_PAGES):
                    if self.stop_requested:
                        break
                    response = await self.http_client.post(
                        f"{base_url}/jobs",
                        json={"appliedFacets": {}, "limit": self.PAGE_SIZE,
                              "offset": offset, "searchText": ""},
                    )
                    data = response.json()
                    jobs = data.get("jobPostings") if isinstance(data, dict) else None
                    if not isinstance(jobs, list) or any(not isinstance(job, dict) for job in jobs):
                        raise ValueError("response jobPostings must be a list of objects")
                    total = data.get("total")
                    if not isinstance(total, int) or total < 0:
                        raise ValueError("response total must be a non-negative integer")
                    # ponytail: detect caps exposed by facets; partition searches to support capped boards.
                    facets = list(data.get("facets") or [])
                    largest_facet = 0
                    while facets:
                        facet = facets.pop()
                        if isinstance(facet, dict):
                            count = facet.get("count")
                            if isinstance(count, int):
                                largest_facet = max(largest_facet, count)
                            facets.extend(facet.get("values") or [])
                    if largest_facet > total and not cap_reported:
                        row["errors"].append(f"listing results capped at {total}; a facet reports {largest_facet} jobs")
                        row["truncated"] = True
                        cap_reported = True
                    row["found"] += len(jobs)
                    ids = [f"{account}:{job['externalPath']}" for job in jobs
                           if isinstance(job.get("externalPath"), str)]
                    known = await sink.contains_many(self.name, ids)
                    missing_dates = 0
                    unseen: list[tuple[dict[str, Any], str, str]] = []
                    for item in jobs:
                        raw_path = item.get("externalPath")
                        raw_id = raw_path.rsplit("/", 1)[-1] if isinstance(raw_path, str) else None
                        source_id = f"{account}:{raw_path}" if raw_path else None
                        if source_id in known:
                            row["skipped"] += 1
                            continue

                        if not raw_path or not raw_id:
                            row["skipped"] += 1
                            row["errors"].append("listing missing externalPath")
                            row["truncated"] = True
                            continue
                        unseen.append((item, raw_path, raw_id))

                    async def fetch_detail(
                        item: dict[str, Any], raw_path: str, raw_id: str
                    ) -> tuple[JobPosting | None, Exception | None]:
                        try:
                            async with detail_limit:
                                detail_response = await self.http_client.get(f"{base_url}{raw_path}")
                            detail_data = detail_response.json()
                            detail = detail_data.get("jobPostingInfo") if isinstance(detail_data, dict) else None
                            if not isinstance(detail, dict):
                                raise ValueError("response jobPostingInfo must be an object")
                            title = detail.get("title") or item.get("title")
                            description = clean_html_to_text(detail.get("jobDescription") or "")
                            posted = parse_to_utc(detail.get("startDate")) or parse_to_utc(item.get("postedOn"))
                            if not posted:
                                raise ValueError("unknown or invalid publication date")
                            if not is_within_days(posted, max_days):
                                return None, None
                            if not title or not description:
                                raise ValueError("detail missing title or description")
                            return JobPosting(
                                source=self.name, source_job_id=f"{account}:{raw_path}",
                                source_url=f"https://{host}{raw_path}", title=title,
                                company_name=name, description_text=description, posted_at=posted,
                                attributes={"location": detail.get("location") or item.get("locationsText"),
                                            "company_slug": account, "external_job_id": raw_id},
                            ), None
                        except Exception as exc:
                            return None, exc

                    results = await asyncio.gather(
                        *(fetch_detail(item, raw_path, raw_id) for item, raw_path, raw_id in unseen)
                    )
                    batch: list[JobPosting] = []
                    for (item, _, raw_id), (job, error) in zip(unseen, results):
                        if error:
                            row["skipped"] += 1
                            if isinstance(error, ValueError) and str(error) == "unknown or invalid publication date":
                                missing_dates += 1
                            else:
                                self.record_error(row, f"detail {raw_id}", error)
                        elif job is not None:
                            batch.append(job)
                        else:
                            row["skipped"] += 1
                    await self.save_jobs(sink, batch, row)
                    self.record_unknown_dates(row, f"page {page + 1}", missing_dates)
                    if offset + len(jobs) >= total:
                        break
                    if not jobs:
                        raise ValueError("pagination ended before reported total")
                    offset += len(jobs)
                else:
                    row["truncated"] = True
                    row["errors"].append(f"page safety limit reached ({self.MAX_PAGES} pages)")
            except Exception as exc:
                self.record_error(row, "listing", exc)
            self.record_account_stats(stats, account, row)

        companies = list(self.companies.items())
        for start in range(0, len(companies), 3):
            if self.stop_requested:
                break
            await asyncio.gather(*(scrape_company(*entry) for entry in companies[start:start + 3]))
        return stats
