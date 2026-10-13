"""Shared runtime and Alembic settings."""

from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        hide_input_in_errors=True,
    )

    database_url: str = Field(default="postgresql+psycopg://postgres:postgrespassword@localhost:5432/job_scrapper", repr=False)
    postgres_host: str = 'localhost'
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_user: str = 'postgres'
    postgres_db: str = 'job_scrapper'
    postgres_password: str | None = Field(default=None, repr=False)
    max_concurrent_requests: int = Field(default=3, ge=1, le=3)
    min_request_delay_seconds: float = Field(default=1.0, ge=1.0, le=3.0)
    max_request_delay_seconds: float = Field(default=3.0, ge=1.0, le=3.0)
    request_timeout_seconds: int = Field(default=30, gt=0)
    source_timeout_seconds: int = Field(default=900, gt=0)
    source_timeouts: dict[str, int] = Field(default_factory=dict)
    http_proxy: str | None = None
    scrape_executor: Literal['memory', 'broker'] = 'memory'
    scrape_broker_url: str | None = Field(default=None, repr=False)
    scrape_broker_stream: str = Field(default='job_scrapper.scrape.v1', min_length=1, max_length=128)
    scrape_max_active_runs: int = Field(default=3, ge=1)
    scrape_max_queued_runs: int = Field(default=20, ge=1)
    api_allowed_hosts: list[str] = Field(default_factory=lambda: ['localhost', '127.0.0.1', 'api'])
    api_allowed_origins: list[str] = Field(default_factory=lambda: [
        f'http://{host}:{port}' for host in ('localhost', '127.0.0.1') for port in (3000, 5173)
    ])

    @field_validator('api_allowed_hosts')
    @classmethod
    def validate_hosts(cls, hosts: list[str]) -> list[str]:
        if not hosts:
            raise ValueError('API_ALLOWED_HOSTS must not be empty')
        if '*' in hosts:
            return ['*']
        if any(not host or any(char in host for char in '/:@?# \t\n') for host in hosts):
            raise ValueError('API_ALLOWED_HOSTS must contain explicit hostnames without ports')
        return [host.lower() for host in hosts]

    @field_validator('source_timeouts')
    @classmethod
    def validate_source_timeouts(cls, values: dict[str, int]) -> dict[str, int]:
        from job_scrapper.connectors.registry import list_connectors
        if set(values) - set(list_connectors()) or any(value <= 0 for value in values.values()):
            raise ValueError('SOURCE_TIMEOUTS must map registered sources to positive seconds')
        return values

    @field_validator('api_allowed_origins')
    @classmethod
    def validate_origins(cls, origins: list[str]) -> list[str]:
        normalized = []
        for origin in origins:
            parsed = urlsplit(origin)
            if (parsed.scheme not in {'http', 'https'} or not parsed.hostname or '*' in origin
                    or parsed.username is not None or parsed.password is not None
                    or parsed.path not in {'', '/'} or parsed.query or parsed.fragment
                    or any(char.isspace() for char in origin)):
                raise ValueError('API_ALLOWED_ORIGINS must contain exact HTTP(S) origins')
            host = parsed.hostname
            if ':' in host:
                host = f'[{host}]'
            port = parsed.port
            suffix = f':{port}' if port is not None and port != (443 if parsed.scheme == 'https' else 80) else ''
            normalized.append(f'{parsed.scheme}://{host}{suffix}')
        return normalized

    @model_validator(mode="after")
    def validate_delay_range(self) -> "Settings":
        if self.postgres_password is not None and 'database_url' not in self.model_fields_set:
            self.database_url = URL.create(
                'postgresql+psycopg', username=self.postgres_user, password=self.postgres_password,
                host=self.postgres_host, port=self.postgres_port, database=self.postgres_db,
            ).render_as_string(hide_password=False)
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
