"""WeWorkRemotely job board connector using RSS feeds."""

from typing import Any
import xml.etree.ElementTree as ET
from job_scrapper.connectors.base import BaseConnector
from job_scrapper.domain.models import JobPosting
from job_scrapper.pipeline.cleaner import clean_html_to_text
from job_scrapper.pipeline.date_parser import is_within_days, parse_to_utc
from job_scrapper.storage.base import JobSink


class WeWorkRemotelyConnector(BaseConnector):
    name: str = "weworkremotely"
    CATEGORY_FEEDS: list[str] = [
        "https://weworkremotely.com/categories/remote-programming-jobs.rss",
        "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
        "https://weworkremotely.com/categories/remote-product-management-jobs.rss",
        "https://weworkremotely.com/categories/remote-data-science-jobs.rss",
        "https://weworkremotely.com/categories/remote-management-and-finance-jobs.rss",
    ]

    async def scrape(self, sink: JobSink, max_days: int = 90) -> dict[str, int]:
        stats = {"found": 0, "inserted": 0, "skipped": 0}

        for feed_url in self.CATEGORY_FEEDS:
            try:
                response = await self.http_client.get(feed_url)
                if response.status_code != 200:
                    continue

                tree = ET.fromstring(response.content)
                items = tree.findall(".//item")
            except Exception:
                continue

            batch: list[JobPosting] = []

            for item in items:
                stats["found"] += 1
                guid_node = item.find("guid")
                title_node = item.find("title")
                pubdate_node = item.find("pubDate")
                desc_node = item.find("description")
                link_node = item.find("link")

                source_id = guid_node.text.strip() if guid_node is not None and guid_node.text else ""
                raw_title = title_node.text.strip() if title_node is not None and title_node.text else "Untitled"
                raw_pubdate = pubdate_node.text.strip() if pubdate_node is not None and pubdate_node.text else ""
                raw_desc = desc_node.text or "" if desc_node is not None else ""
                source_url = link_node.text.strip() if link_node is not None and link_node.text else ""

                pub_date = parse_to_utc(raw_pubdate)
                if not pub_date or not is_within_days(pub_date, max_days=max_days):
                    stats["skipped"] += 1
                    continue

                if source_id and await sink.contains(self.name, source_id):
                    stats["skipped"] += 1
                    continue

                # Parse company name and clean title: format usually "Company: Title"
                company_name = "Unknown Company"
                title = raw_title
                if ": " in raw_title:
                    parts = raw_title.split(": ", 1)
                    company_name = parts[0].strip()
                    title = parts[1].strip()

                clean_desc = clean_html_to_text(raw_desc)

                attributes: dict[str, Any] = {
                    "work_arrangement": "remote",
                    "location": "Remote Worldwide",
                    "feed_url": feed_url,
                }

                job = JobPosting(
                    source=self.name,
                    source_job_id=source_id or source_url,
                    source_url=source_url,
                    title=title,
                    company_name=company_name,
                    description_text=clean_desc,
                    posted_at=pub_date,
                    attributes=attributes,
                )
                batch.append(job)

            if batch:
                inserted = await sink.save_batch(batch)
                stats["inserted"] += inserted
                stats["skipped"] += len(batch) - inserted

        return stats
