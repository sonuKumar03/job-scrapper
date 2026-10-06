"""Shared runtime and Alembic settings."""

from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://postgres:postgrespassword@localhost:5432/job_scrapper"
    max_concurrent_requests: int = Field(default=3, ge=1, le=3)
    min_request_delay_seconds: float = Field(default=1.0, ge=1.0, le=3.0)
    max_request_delay_seconds: float = Field(default=3.0, ge=1.0, le=3.0)
    request_timeout_seconds: int = Field(default=30, gt=0)
    http_proxy: str | None = None
    scrape_executor: Literal['memory', 'broker'] = 'memory'
    scrape_broker_url: str | None = Field(default=None, repr=False)
    scrape_broker_stream: str = Field(default='job_scrapper.scrape.v1', min_length=1, max_length=128)
    scrape_max_active_runs: int = Field(default=3, ge=1)
    scrape_max_queued_runs: int = Field(default=20, ge=1)

    @model_validator(mode="after")
    def validate_delay_range(self) -> "Settings":
        if self.min_request_delay_seconds > self.max_request_delay_seconds:
            raise ValueError("MIN_REQUEST_DELAY_SECONDS must not exceed MAX_REQUEST_DELAY_SECONDS")
        if self.scrape_executor == 'broker' and not self.scrape_broker_url:
            raise ValueError('SCRAPE_BROKER_URL is required for broker mode')
        if self.scrape_broker_url:
            parsed = urlsplit(self.scrape_broker_url)
            if parsed.scheme not in {'redis', 'rediss'} or not parsed.hostname:
                raise ValueError('SCRAPE_BROKER_URL must use redis:// or rediss:// with a hostname')
        return self


def normalize_database_url(database_url: str) -> str:
    """Use the installed psycopg driver when a generic PostgreSQL URL is given."""
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
