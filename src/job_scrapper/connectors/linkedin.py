"""Recent public LinkedIn job listings and their JobPosting metadata."""

import asyncio
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

from selectolax.lexbor import LexborHTMLParser

from job_scrapper.connectors.base import BaseConnector
from job_scrapper.domain.models import JobPosting
from job_scrapper.execution.cancellation import RequestStopped
from job_scrapper.pipeline.cleaner import clean_html_to_text
from job_scrapper.pipeline.date_parser import is_within_days, parse_to_utc
from job_scrapper.pipeline.job_metadata import parse_job_metadata, parse_linkedin_closure
from job_scrapper.storage.base import JobSink


class LinkedInConnector(BaseConnector):
    name = "linkedin"
    SEARCH_URL = "https://www.linkedin.com/jobs/search/"
    MAX_PAGES = 40
    SEARCH_QUERIES = (
        'software engineer', 'software developer', 'frontend engineer',
        'backend engineer', 'full stack engineer', 'devops engineer',
        'data engineer', 'qa engineer', 'mobile engineer', 'site reliability engineer',
    )

    async def _fetch_job(self, source_id: str, url: str, max_days: int,
                         stats: dict[str, Any]) -> JobPosting | None:
        parsing = False
        stats['detail_attempted'] += 1
        try:
            response = await self.http_client.get(url)
            parsing = True
            page = LexborHTMLParser(response.text)
            closure = parse_linkedin_closure(response.text)
            status_attributes = {
                'posting_status': 'closed' if closure else 'unknown',
                'posting_status_checked_at': datetime.now(timezone.utc).isoformat(),
            }
            if closure:
                status_attributes['posting_status_evidence'] = closure
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
            location = item.get("jobLocation") or {}
            address = location.get("address") if isinstance(location, dict) else None
            if not isinstance(address, dict):
                address = {}
            job = JobPosting(
                source=self.name,
                source_job_id=source_id,
                source_url=url,
                title=item["title"],
                company_name=company,
                description_text=description,
                posted_at=posted_at,
                attributes={
                    **status_attributes,
                    "location": ", ".join(str(address[key]) for key in
                                          ("addressLocality", "addressRegion", "addressCountry")
                                          if address.get(key)) or None,
                    "employment_type": item.get("employmentType"),
                    "work_arrangement": "remote" if item.get("jobLocationType") == "TELECOMMUTE" else "unknown",
                },
            )
            stats['detail_valid'] += 1
            stats['closed'] += int(closure is not None)
            return job
        except RequestStopped:
            stats['detail_attempted'] -= 1
            return None
        except (ValueError, TypeError, AttributeError) as exc:
            if parsing:
                stats['detail_invalid'] += 1
            self.record_error(stats, f"job {source_id}", exc)
            stats['skipped'] += 1
            return None
        except Exception as exc:
            self.record_error(stats, f"job {source_id}", exc)
            stats["skipped"] += 1
            return None

    async def scrape(self, sink: JobSink, max_days: int = 7) -> dict[str, Any]:
        stats = self.new_stats()
        stats.update(dict.fromkeys(self.DIAGNOSTIC_COUNTS, 0))
        seen_ids: set[str] = set()
        active_queries: dict[str, set[str]] = {keyword: set() for keyword in self.SEARCH_QUERIES}
        # Rotate searches so a large role family cannot consume the entire source budget.
        for page_number in range(self.MAX_PAGES):
            for keyword in tuple(active_queries):
                if self.stop_requested:
                    return stats
                query = urlencode({"keywords": keyword, "location": "India",
                                   "f_TPR": f"r{max_days * 86400}", "start": page_number * 25})
                try:
                    response = await self.http_client.get(f"{self.SEARCH_URL}?{query}")
                    page = LexborHTMLParser(response.text)
                    stats['listing_pages'] += 1
                    links: dict[str, str] = {}
                    for anchor in page.css('a[href*="/jobs/view/"]'):
                        parsed = urlsplit(anchor.attributes.get("href", ""))
                        match = re.search(r"-(\d+)$", parsed.path)
                        if match:
                            links[match.group(1)] = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
                    if not links and page_number == 0:
                        stats['truncated'] = True
                        stats['errors'].append(f'search {keyword}: no job links on first listing page')
                except Exception as exc:
                    self.record_error(stats, f"search {keyword}, page {page_number + 1}", exc)
                    del active_queries[keyword]
                    continue
                if not links:
                    del active_queries[keyword]
                    continue
                if not links.keys() - active_queries[keyword]:
                    stats['truncated'] = True
                    stats['errors'].append(f'search {keyword}, page {page_number + 1}: repeated listings; coverage incomplete')
                    del active_queries[keyword]
                    continue
                active_queries[keyword].update(links)
                fresh_links = [(source_id, url) for source_id, url in links.items() if source_id not in seen_ids]
                seen_ids.update(links)
                stats["found"] += len(fresh_links)
                known_ids = await sink.contains_many(self.name, [source_id for source_id, _ in fresh_links])
                new_links = [(source_id, url) for source_id, url in fresh_links if source_id not in known_ids]
                stats["skipped"] += len(fresh_links) - len(new_links)
                await self.save_jobs(sink, [], stats)
                jobs: list[JobPosting] = []
                tasks = [asyncio.create_task(self._fetch_job(source_id, url, max_days, stats))
                         for source_id, url in new_links]
                try:
                    for completed in asyncio.as_completed(tasks):
                        job = await completed
                        if job is not None:
                            jobs.append(job)
                        if len(jobs) >= 10:
                            await self.save_jobs(sink, jobs, stats)
                            jobs.clear()
                    await self.save_jobs(sink, jobs, stats)
                finally:
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
            if not active_queries:
                break
        if active_queries and not self.stop_requested:
            stats["truncated"] = True
            stats["errors"].append(f"page safety limit reached ({self.MAX_PAGES} pages per search): {', '.join(active_queries)}")
        return stats
