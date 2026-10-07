"""SQLAlchemy ORM models for PostgreSQL persistence."""

from datetime import datetime, timezone
from typing import Any
import uuid
from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class CompanyModel(Base):
    __tablename__ = 'companies'

    company_key: Mapped[str] = mapped_column(String(256), primary_key=True)
    company_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    directory_status: Mapped[str] = mapped_column(String(32), nullable=False)


class CompanyTargetModel(Base):
    __tablename__ = 'company_targets'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_key: Mapped[str] = mapped_column(String(256), ForeignKey('companies.company_key', ondelete='CASCADE'), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    account_key: Mapped[str] = mapped_column(String(256), nullable=False)
    board_url: Mapped[str] = mapped_column(Text, nullable=False)
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    provenance: Mapped[str] = mapped_column(Text, nullable=False)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    succeeded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint('provider', 'account_key', name='uq_company_targets_provider_account'),
        CheckConstraint("provider IN ('greenhouse', 'lever', 'ashby', 'workday', 'workable')", name='ck_company_targets_provider'),
        CheckConstraint("verification_status IN ('supported', 'needs_review', 'unsupported', 'unavailable', 'blocked', 'unverified')", name='ck_company_targets_status'),
        Index('ix_company_targets_provider_enabled', 'provider', 'enabled'),
    )


class JobModel(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    source_job_id: Mapped[str] = mapped_column(String(256), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    company_name: Mapped[str] = mapped_column(Text, index=True, nullable=False)
    description_text: Mapped[str] = mapped_column(Text, nullable=False)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    content_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    canonical_signature: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    simhash: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}", nullable=False)

    sightings: Mapped[list["JobSightingModel"]] = relationship(
        "JobSightingModel", back_populates="job", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("source", "source_job_id", name="uq_jobs_source_job_id"),
    )


class JobSightingModel(Base):
    """Ledger of job sightings across different sources (Layer 3 entity resolution)."""

    __tablename__ = "job_sightings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    source_job_id: Mapped[str] = mapped_column(String(256), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    job: Mapped[JobModel] = relationship("JobModel", back_populates="sightings")

    __table_args__ = (
        UniqueConstraint("source", "source_job_id", name="uq_sightings_source_job_id"),
    )


class ScrapeRunModel(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False)
    jobs_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_inserted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class ScrapeExecutionModel(Base):
    """One CLI or dashboard invocation, with durable source/account results."""

    __tablename__ = "scrape_executions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sources: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    days: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    executor_mode: Mapped[str] = mapped_column(String(16), nullable=False, default='memory')
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempt_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    results: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class ScrapeDispatchModel(Base):
    """One transactional dispatch intent per execution; retries advance generation."""

    __tablename__ = 'scrape_dispatches'

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('scrape_executions.id', ondelete='CASCADE'), primary_key=True
    )
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    dispatched_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
