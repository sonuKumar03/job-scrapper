"""Immutable company targets; no storage or connector dependencies."""

import re
from typing import Literal, Protocol
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ATS_PROVIDERS = frozenset({'greenhouse', 'lever', 'ashby', 'workday', 'workable'})
VerificationStatus = Literal['supported', 'needs_review', 'unsupported', 'unavailable', 'blocked', 'unverified']


class CompanyCatalogUnavailable(RuntimeError):
    """Catalog infrastructure failed; retry instead of reporting empty coverage."""


class Company(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid', str_strip_whitespace=True)

    company_key: str
    company_name: str
    source_url: str
    directory_status: VerificationStatus = 'needs_review'

    @field_validator('company_key', 'company_name', 'source_url')
    @classmethod
    def nonempty(cls, value: str) -> str:
        if not value:
            raise ValueError('company fields must not be empty')
        return value

    @field_validator('source_url')
    @classmethod
    def absolute_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('company source must be an absolute public URL')
        return value


class CompanyTarget(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid', str_strip_whitespace=True)

    company_key: str
    company_name: str
    provider: Literal['greenhouse', 'lever', 'ashby', 'workday', 'workable']
    account_key: str
    board_url: str
    verification_status: VerificationStatus
    enabled: bool = Field(strict=True)
    provenance: str = 'catalog_seed'

    @model_validator(mode='after')
    def valid_board(self) -> 'CompanyTarget':
        if not self.company_key or not self.company_name or not self.provenance:
            raise ValueError('target identity and provenance must not be empty')
        pattern = r'[A-Za-z0-9][A-Za-z0-9_.-]*'
        parts = self.account_key.split(':') if self.provider == 'workday' else [self.account_key]
        if len(parts) != (2 if self.provider == 'workday' else 1) or any(not re.fullmatch(pattern, part) for part in parts):
            raise ValueError('invalid provider account key')
        parsed = urlsplit(self.board_url)
        host = parsed.hostname or ''
        allowed = {
            'greenhouse': {'boards.greenhouse.io', 'job-boards.greenhouse.io'},
            'lever': {'jobs.lever.co'},
            'ashby': {'jobs.ashbyhq.com'},
            'workable': {'apply.workable.com'},
        }
        host_ok = bool(re.fullmatch(r'[A-Za-z0-9-]+\.wd[0-9]+\.myworkdayjobs\.com', host)) if self.provider == 'workday' else host in allowed[self.provider]
        if parsed.scheme != 'https' or not host_ok or parsed.username or parsed.password or parsed.port not in {None, 443}:
            raise ValueError('board URL must use its public HTTPS ATS host')
        return self


class SeedReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    inserted_companies: int = 0
    inserted_targets: int = 0
    conflicts: tuple[str, ...] = ()


class CompanyTargetRepository(Protocol):
    async def ensure_seed(self, companies: tuple[Company, ...], targets: tuple[CompanyTarget, ...]) -> SeedReport: ...
    async def list_enabled(self, provider: str) -> tuple[CompanyTarget, ...]: ...
    async def status_counts(self) -> dict[str, int]: ...


def validate_targets(targets: tuple[CompanyTarget, ...], provider: str) -> None:
    if not targets:
        raise ValueError('no enabled company targets')
    if any(t.provider != provider or not t.enabled for t in targets):
        raise ValueError('targets must be enabled and belong to this provider')
    if len({t.account_key for t in targets}) != len(targets):
        raise ValueError('duplicate company account')
