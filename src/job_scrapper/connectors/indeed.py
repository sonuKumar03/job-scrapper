"""Indeed public search cards with their selected full descriptions."""

import asyncio
import json
from typing import Any
from urllib.parse import urlencode

from selectolax.lexbor import LexborHTMLParser

from job_scrapper.connectors.base import BaseConnector
from job_scrapper.domain.models import JobPosting
from job_scrapper.pipeline.cleaner import clean_html_to_text
from job_scrapper.pipeline.date_parser import is_within_days, parse_to_utc
from job_scrapper.storage.base import JobSink


class IndeedConnector(BaseConnector):
    name = "indeed"
    SEARCH_URL = "https://in.indeed.com/jobs"
    MAX_PAGES = 100

    async def _fetch_job(self, card: dict[str, Any], search_url: str,
                         posted_at: Any, stats: dict[str, Any]) -> JobPosting | None:
        source_id = card["jobkey"]
        try:
            response = await self.http_client.get(f"{search_url}&vjk={source_id}")
            page = LexborHTMLParser(response.text)
            body = page.css_first("div.react-native-html-content.simple-job-description-html")
            description = clean_html_to_text(body.html if body else "")
            if not all(isinstance(value, str) and value.strip() for value in
                       (card.get("displayTitle"), card.get("company"), description)):
                raise ValueError("missing title, company, or full description")
            return JobPosting(
                source=self.name,
                source_job_id=source_id,
                source_url=f"https://in.indeed.com/viewjob?jk={source_id}",
                title=card["displayTitle"],
                company_name=card["company"],
                description_text=description,
                posted_at=posted_at,
                attributes={"location": card.get("formattedLocation"),
                            "work_arrangement": "unknown"},
            )
        except Exception as exc:
            self.record_error(stats, f"job {source_id}", exc)
            stats["skipped"] += 1
            return None

    async def scrape(self, sink: JobSink, max_days: int = 7) -> dict[str, Any]:
        stats = self.new_stats()
        seen_ids: set[str] = set()
        for page_number in range(self.MAX_PAGES):
            if self.stop_requested:
                break
            query = urlencode({"q": "software engineer", "fromage": max_days,
                               "start": page_number * 10})
            search_url = f"{self.SEARCH_URL}?{query}"
            try:
                response = await self.http_client.get(search_url)
                page = LexborHTMLParser(response.text)
                script = page.css_first("script#mosaic-data")
                if script is None:
                    raise ValueError("missing search card data")
                marker = 'window.mosaic.providerData["mosaic-provider-jobcards"]='
                source = script.text()
                offset = source.index(marker) + len(marker)
                data = json.JSONDecoder().raw_decode(source[offset:])[0]
                cards = data["metaData"]["mosaicProviderJobCardsModel"]["results"]
                if not isinstance(cards, list) or (page_number == 0 and not cards):
                    raise ValueError("no search cards")
                fresh = [card for card in cards if isinstance(card, dict)
                         and isinstance(card.get("jobkey"), str)
                         and card["jobkey"] not in seen_ids]
                seen_ids.update(card["jobkey"] for card in fresh)
            except Exception as exc:
                self.record_error(stats, f"page {page_number + 1}", exc)
                break
            if not fresh:
                break

            stats["found"] += len(fresh)
            known_ids = await sink.contains_many(self.name, [card["jobkey"] for card in fresh])
            new_cards = []
            for card in fresh:
                if card["jobkey"] in known_ids:
                    stats["skipped"] += 1
                    continue
                posted_at = parse_to_utc(card.get("pubDate"))
                if posted_at is None:
                    self.record_unknown_dates(stats, f"job {card['jobkey']}", 1)
                    stats["skipped"] += 1
                elif is_within_days(posted_at, max_days):
                    new_cards.append((card, posted_at))
                else:
                    stats["skipped"] += 1
            jobs = await asyncio.gather(*(self._fetch_job(card, search_url, posted_at, stats)
                                          for card, posted_at in new_cards))
            await self.save_jobs(sink, [job for job in jobs if job is not None], stats)
            if not any(f"start={((page_number + 1) * 10)}" in
                       anchor.attributes.get("href", "") for anchor in page.css('a[href*="start="]')):
                break
        else:
            stats["truncated"] = True
            stats["errors"].append(f"page safety limit reached ({self.MAX_PAGES} pages)")
        return stats
