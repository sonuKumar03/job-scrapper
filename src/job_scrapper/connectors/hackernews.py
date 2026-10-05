"""Hacker News 'Who is hiring?' community connector using Algolia API."""

import html
import re
from typing import Any
from job_scrapper.connectors.base import BaseConnector
from job_scrapper.domain.models import JobPosting
from job_scrapper.pipeline.cleaner import clean_html_to_text
from job_scrapper.pipeline.date_parser import is_within_days, parse_to_utc
from job_scrapper.storage.base import JobSink


class HackerNewsConnector(BaseConnector):
    name: str = "hackernews"
    SEARCH_URL: str = "https://hn.algolia.com/api/v1/search_by_date"

    async def scrape(self, sink: JobSink, max_days: int = 90) -> dict[str, int]:
        stats = {"found": 0, "inserted": 0, "skipped": 0}

        # 1. Discover recent "Ask HN: Who is hiring?" thread IDs
        story_query_url = f"{self.SEARCH_URL}?tags=ask_hn&query=Who%20is%20hiring&hitsPerPage=5"
        try:
            resp = await self.http_client.get(story_query_url)
            if resp.status_code != 200:
                return stats
            data = resp.json()
            stories = [
                h for h in data.get("hits", [])
                if "Who is hiring?" in h.get("title", "")
            ]
        except Exception:
            return stats

        for story in stories:
            story_id = story.get("objectID")
            if not story_id:
                continue

            comments_url = f"{self.SEARCH_URL}?tags=comment,story_{story_id}&hitsPerPage=500"
            try:
                c_resp = await self.http_client.get(comments_url)
                if c_resp.status_code != 200:
                    continue
                c_data = c_resp.json()
                comments = c_data.get("hits", [])
            except Exception:
                continue

            batch: list[JobPosting] = []

            for comment in comments:
                # Only include top-level comments (direct job postings)
                if str(comment.get("parent_id")) != str(story_id):
                    continue

                stats["found"] += 1
                comment_id = str(comment.get("objectID"))
                created_at = comment.get("created_at")
                pub_date = parse_to_utc(created_at)

                if not pub_date or not is_within_days(pub_date, max_days=max_days):
                    stats["skipped"] += 1
                    continue

                if await sink.contains(self.name, comment_id):
                    stats["skipped"] += 1
                    continue

                raw_html = comment.get("comment_text") or ""
                clean_text = clean_html_to_text(html.unescape(raw_html))
                if len(clean_text) < 40:  # Skip trivial non-job remarks
                    stats["skipped"] += 1
                    continue

                first_line = clean_text.split("\n")[0][:300]
                company_name = "HN Startup"
                title = "Software Engineer"
                work_arrangement = "unknown"

                # Parse header format: Company | Title | Location | Remote/Onsite
                if "|" in first_line:
                    segments = [s.strip() for s in first_line.split("|")]
                    if len(segments) >= 1 and segments[0]:
                        company_name = segments[0][:200]
                    if len(segments) >= 2 and segments[1]:
                        title = segments[1][:200]

                lower_text = clean_text.lower()
                if "remote" in lower_text:
                    work_arrangement = "remote"
                elif "hybrid" in lower_text:
                    work_arrangement = "hybrid"
                elif "onsite" in lower_text or "on-site" in lower_text:
                    work_arrangement = "in-office"

                attributes: dict[str, Any] = {
                    "work_arrangement": work_arrangement,
                    "author": comment.get("author"),
                    "hn_story_id": story_id,
                }

                job = JobPosting(
                    source=self.name,
                    source_job_id=comment_id,
                    source_url=f"https://news.ycombinator.com/item?id={comment_id}",
                    title=title,
                    company_name=company_name,
                    description_text=clean_text,
                    posted_at=pub_date,
                    attributes=attributes,
                )
                batch.append(job)

            if batch:
                inserted = await sink.save_batch(batch)
                stats["inserted"] += inserted
                stats["skipped"] += len(batch) - inserted

        return stats
