"""Domain models for Job Scrapper."""

from datetime import datetime, timezone
import hashlib
from typing import Any
from pydantic import BaseModel, Field


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
    attributes: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        """Automatically compute content_hash if not provided."""
        if not self.content_hash:
            # Hash company + title + first 250 characters of description
            raw_signature = f"{self.company_name.strip().lower()}|{self.title.strip().lower()}|{self.description_text[:250].strip().lower()}"
            self.content_hash = hashlib.sha256(raw_signature.encode("utf-8")).hexdigest()
