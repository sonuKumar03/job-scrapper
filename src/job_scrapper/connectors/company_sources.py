"""Packaged directory of company career pages and supported ATS accounts."""

import json
from dataclasses import dataclass
from importlib.resources import files
from typing import Literal
from urllib.parse import urlsplit

CompanySourceStatus = Literal[
    "supported", "needs_review", "unsupported", "unavailable", "blocked"
]
_STATUSES = {"supported", "needs_review", "unsupported", "unavailable", "blocked"}


@dataclass(frozen=True, slots=True)
class CompanySource:
    company_key: str
    company_name: str
    source_url: str
    provider: str | None
    account_key: str | None
    status: CompanySourceStatus
    board_url: str | None = None


def load_company_sources(provider: str | None = None) -> list[CompanySource]:
    """Load validated company source records, optionally for one provider."""
    raw_sources = json.loads(
        files("job_scrapper").joinpath("company_sources.json").read_text(encoding="utf-8")
    )
    if not isinstance(raw_sources, list):
        raise ValueError("company source catalog must be a list")

    sources: list[CompanySource] = []
    company_keys: set[str] = set()
    for index, raw in enumerate(raw_sources):
        if not isinstance(raw, dict):
            raise ValueError(f"company source {index} must be an object")
        company_key = raw.get("company_key")
        company_name = raw.get("company_name")
        source_url = raw.get("source_url")
        source_provider = raw.get("provider")
        account_key = raw.get("account_key")
        status = raw.get("status")
        board_url = raw.get("board_url")

        if not all(isinstance(value, str) and value.strip() for value in
                   (company_key, company_name, source_url)):
            raise ValueError(f"company source {index} has missing required text")
        if company_key in company_keys:
            raise ValueError(f"duplicate company key: {company_key}")
        company_keys.add(company_key)

        parsed_url = urlsplit(source_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError(f"company source {company_key} has an invalid URL")
        if board_url is not None:
            if not isinstance(board_url, str):
                raise ValueError(f"company source {company_key} has an invalid board URL")
            parsed_board_url = urlsplit(board_url)
            if parsed_board_url.scheme not in {"http", "https"} or not parsed_board_url.netloc:
                raise ValueError(f"company source {company_key} has an invalid board URL")
        if source_provider is not None and (not isinstance(source_provider, str) or not source_provider.strip()):
            raise ValueError(f"company source {company_key} has an invalid provider")
        if account_key is not None and (not isinstance(account_key, str) or not account_key.strip()):
            raise ValueError(f"company source {company_key} has an invalid account key")
        if status not in _STATUSES:
            raise ValueError(f"company source {company_key} has an invalid status")
        if status == "supported" and (not source_provider or not account_key):
            raise ValueError(f"supported company source {company_key} needs provider and account key")

        source = CompanySource(
            company_key=company_key,
            company_name=company_name,
            source_url=source_url,
            provider=source_provider,
            account_key=account_key,
            status=status,
            board_url=board_url,
        )
        if provider is None or source.provider == provider.lower():
            sources.append(source)
    return sources
