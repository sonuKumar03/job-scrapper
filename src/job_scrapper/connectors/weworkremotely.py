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
    CATEGORY_FEEDS: list[str] = ["https://weworkremotely.com/remote-jobs.rss"]

    async def scrape(self, sink: JobSink, max_days: int = 7) -> dict[str, Any]:
        stats = self.new_stats()

        for feed_url in self.CATEGORY_FEEDS:
            if self.stop_requested:
                break
            try:
                response = await self.http_client.get(feed_url)
                tree = ET.fromstring(response.content)
                items = tree.findall(".//item")
            except Exception as exc:
                self.record_error(stats, "feed", exc)
                continue

            batch: list[JobPosting] = []
            identities = []
            for item in items:
                guid = item.findtext("guid")
                link = item.findtext("link")
                if guid or link:
                    identities.append((guid or link).strip())
            known_ids = await sink.contains_many(self.name, identities)

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

                if (source_id or source_url) in known_ids:
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

            await self.save_jobs(sink, batch, stats)

        return stats
