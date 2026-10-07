"""Domain models for Job Scrapper."""

from datetime import datetime, timezone
from html import unescape
from typing import Any
from pydantic import BaseModel, Field, ValidationInfo, field_validator
from job_scrapper.pipeline.hasher import compute_content_hash
from job_scrapper.pipeline.attributes import normalize_attributes


class JobPosting(BaseModel):
    """Normalized job posting contract across all scrapers."""

    source: str
    source_job_id: str
    source_url: str
    title: str
    company_name: str
    description_text: str
    posted_at: datetime
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    content_hash: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict, validate_default=True)

    @field_validator("attributes")
    @classmethod
    def normalize_attribute_fields(cls, value: dict[str, Any], info: ValidationInfo) -> dict[str, Any]:
        return normalize_attributes(value, info.data.get("description_text", ""))

    @field_validator("source", "source_job_id", "source_url", "title", "company_name", "description_text")
    @classmethod
    def require_nonblank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("title", mode="before")
    @classmethod
    def decode_title_entities(cls, value: Any) -> Any:
        return unescape(value) if isinstance(value, str) else value

    @field_validator("posted_at")
    @classmethod
    def normalize_posted_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        if value > datetime.now(timezone.utc):
            raise ValueError("posted_at must not be in the future")
        return value

    @field_validator("scraped_at")
    @classmethod
    def normalize_scraped_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def model_post_init(self, __context: Any) -> None:
        """Automatically compute content_hash if not provided."""
        if not self.content_hash:
            self.content_hash = compute_content_hash(
                self.company_name, self.title, self.description_text
            )
