"""Hacker News hiring threads through the paginated Algolia search API."""

from datetime import datetime, timedelta, timezone
import html
from typing import Any
from urllib.parse import urlencode
from job_scrapper.connectors.base import BaseConnector
from job_scrapper.domain.models import JobPosting
from job_scrapper.pipeline.cleaner import clean_html_to_text
from job_scrapper.pipeline.date_parser import is_within_days, parse_to_utc
from job_scrapper.storage.base import JobSink


class HackerNewsConnector(BaseConnector):
    name: str = "hackernews"
    SEARCH_URL: str = "https://hn.algolia.com/api/v1/search_by_date"
    HITS_PER_PAGE: int = 100
    MAX_PAGES: int = 10

    async def _fetch_page(
        self, params: dict[str, str | int], context: str, stats: dict[str, Any]
    ) -> dict[str, Any] | None:
        try:
            response = await self.http_client.get(f"{self.SEARCH_URL}?{urlencode(params)}")
            data = response.json()
            if (
                not isinstance(data, dict)
                or not isinstance(data.get("hits"), list)
                or not isinstance(data.get("nbPages"), int)
                or ("nbHits" in data and not isinstance(data["nbHits"], int))
                or any(not isinstance(hit, dict) for hit in data["hits"])
            ):
                raise ValueError("response hits and nbPages have invalid types")
            return data
        except Exception as exc:
            self.record_error(stats, context, exc)
            return None

    async def scrape(self, sink: JobSink, max_days: int = 7) -> dict[str, Any]:
        stats = self.new_stats()
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)
        numeric_filter = f"created_at_i>{int(cutoff.timestamp())}"
        stories: list[dict[str, Any]] = []
        story_ids: set[str] = set()
        story_pages = 0

        for page in range(self.MAX_PAGES):
            data = await self._fetch_page(
                {
                    "tags": "ask_hn",
                    "query": "Who is hiring",
                    "numericFilters": numeric_filter,
                    "hitsPerPage": self.HITS_PER_PAGE,
                    "page": page,
                },
                f"story search page {page + 1}",
                stats,
            )
            if data is None:
                return stats
            if data.get("nbHits", 0) > self.MAX_PAGES * self.HITS_PER_PAGE:
                stats["truncated"] = True
                stats["errors"].append(f"story search exceeds the {self.MAX_PAGES * self.HITS_PER_PAGE}-result API window")
            story_pages = data["nbPages"]
            for story in data["hits"]:
                story_id = str(story.get("objectID") or "")
                if not story_id or story_id in story_ids:
                    self.record_error(stats, f"story search page {page + 1}", ValueError("missing or repeated story id"))
                    return stats
                story_ids.add(story_id)
                if "Who is hiring?" not in story.get("title", ""):
                    continue
                stories.append(story)
            if page + 1 >= story_pages:
                break
        if story_pages > self.MAX_PAGES:
            stats["truncated"] = True
            stats["errors"].append(f"story feed has {story_pages} pages; limit is {self.MAX_PAGES}")

        unknown_dates = 0
        for story in stories:
            story_id = str(story["objectID"])
            comment_ids: set[str] = set()
            comment_pages = 0
            for page in range(self.MAX_PAGES):
                data = await self._fetch_page(
                    {
                        "tags": f"comment,story_{story_id}",
                        "numericFilters": numeric_filter,
                        "hitsPerPage": self.HITS_PER_PAGE,
                        "page": page,
                    },
                    f"story {story_id} page {page + 1}",
                    stats,
                )
                if data is None:
                    break
                if data.get("nbHits", 0) > self.MAX_PAGES * self.HITS_PER_PAGE:
                    stats["truncated"] = True
                    stats["errors"].append(f"story {story_id} exceeds the {self.MAX_PAGES * self.HITS_PER_PAGE}-result API window")
                comment_pages = data["nbPages"]
                page_ids = [str(hit.get("objectID") or "") for hit in data["hits"]]
                if not all(page_ids) or any(comment_id in comment_ids for comment_id in page_ids):
                    self.record_error(stats, f"story {story_id} page {page + 1}", ValueError("missing or repeated result id"))
                    break
                comment_ids.update(page_ids)
                batch: list[JobPosting] = []
                for comment in data["hits"]:
                    if str(comment.get("parent_id")) != story_id:
                        continue
                    stats["found"] += 1
                    comment_id = str(comment.get("objectID") or "")
                    pub_date = parse_to_utc(comment.get("created_at"))
                    if not pub_date:
                        unknown_dates += 1
                        stats["skipped"] += 1
                        continue
                    if not is_within_days(pub_date, max_days=max_days):
                        stats["skipped"] += 1
                        continue
                    if await sink.contains(self.name, comment_id):
                        stats["skipped"] += 1
                        continue

                    clean_text = clean_html_to_text(html.unescape(comment.get("comment_text") or ""))
                    if len(clean_text) < 40:
                        stats["skipped"] += 1
                        continue
                    first_line = clean_text.split("\n")[0][:300]
                    company_name, title = "HN Startup", "Software Engineer"
                    if "|" in first_line:
                        segments = [part.strip() for part in first_line.split("|")]
                        company_name = (segments[0] or company_name)[:200]
                        if len(segments) > 1 and segments[1]:
                            title = segments[1][:200]
                    lower_text = clean_text.lower()
                    work_arrangement = (
                        "remote" if "remote" in lower_text else
                        "hybrid" if "hybrid" in lower_text else
                        "in-office" if "onsite" in lower_text or "on-site" in lower_text else
                        "unknown"
                    )
                    batch.append(JobPosting(
                        source=self.name,
                        source_job_id=comment_id,
                        source_url=f"https://news.ycombinator.com/item?id={comment_id}",
                        title=title,
                        company_name=company_name,
                        description_text=clean_text,
                        posted_at=pub_date,
                        attributes={"work_arrangement": work_arrangement, "author": comment.get("author"), "hn_story_id": story_id},
                    ))
                if batch:
                    inserted = await sink.save_batch(batch)
                    stats["inserted"] += inserted
                    stats["skipped"] += len(batch) - inserted
                if page + 1 >= comment_pages:
                    break
            if comment_pages > self.MAX_PAGES:
                stats["truncated"] = True
                stats["errors"].append(f"story {story_id} has {comment_pages} comment pages; limit is {self.MAX_PAGES}")

        self.record_unknown_dates(stats, "comments", unknown_dates)
        return stats
