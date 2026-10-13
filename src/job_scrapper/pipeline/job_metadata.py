"""Extract a JobPosting object from JSON-LD script contents."""

import json
from collections.abc import Iterable
from typing import Any

from selectolax.lexbor import LexborHTMLParser


def parse_linkedin_closure(html: str) -> str | None:
    page = LexborHTMLParser(html)
    for banner in page.css('.top-card-layout .closed-job__flavor, .topcard .closed-job__flavor'):
        parent = banner
        while parent is not None:
            classes = (parent.attributes.get('class') or '').split()
            if 'show-more-less-html__markup' in classes or 'description__text' in classes:
                break
            parent = parent.parent
        if parent is not None:
            continue
        text = ' '.join(banner.text().split())
        if text:
            return text
    return None


def parse_job_metadata(scripts: Iterable[str]) -> dict[str, Any]:
    for script in scripts:
        try:
            pending = [json.loads(script)]
        except json.JSONDecodeError:
            continue
        while pending:
            value = pending.pop()
            if isinstance(value, list):
                pending.extend(reversed(value))
            elif isinstance(value, dict):
                types = value.get("@type")
                if types == "JobPosting" or isinstance(types, list) and "JobPosting" in types:
                    return value
                if "@graph" in value:
                    pending.append(value["@graph"])
    raise ValueError("missing JobPosting metadata")
