from datetime import datetime, timedelta, timezone
import pytest
from pydantic import ValidationError
from job_scrapper.domain.models import JobPosting
from job_scrapper.storage.memory import InMemoryJobSink


def test_job_posting_rejects_blank_required_text() -> None:
    values = {
        "source": "test_source",
        "source_job_id": "101",
        "source_url": "https://example.com/job/101",
        "title": "Engineer",
        "company_name": "Acme",
        "description_text": "Build software",
        "posted_at": datetime.now(timezone.utc),
    }
    for field in ("source", "source_job_id", "source_url", "title", "company_name", "description_text"):
        with pytest.raises(ValidationError):
            JobPosting(**{**values, field: "  "})


def test_job_posting_normalizes_naive_dates_and_rejects_future_dates() -> None:
    values = {
        "source": "test_source",
        "source_job_id": "101",
        "source_url": "https://example.com/job/101",
        "title": "Engineer",
        "company_name": "Acme",
        "description_text": "Build software",
    }
    job = JobPosting(**values, posted_at=datetime(2026, 1, 1))
    assert job.posted_at.tzinfo == timezone.utc
    with pytest.raises(ValidationError):
        JobPosting(**values, posted_at=datetime.now(timezone.utc) + timedelta(days=1))


def test_job_posting_hash_uses_full_description() -> None:
    values = {
        "source": "test_source",
        "source_url": "https://example.com/job/101",
        "title": "Engineer",
        "company_name": "Acme",
        "posted_at": datetime.now(timezone.utc),
    }
    first = JobPosting(source_job_id="101", description_text="x" * 250 + "Python", **values)
    second = JobPosting(source_job_id="102", description_text="x" * 250 + "Kotlin", **values)
    assert first.content_hash != second.content_hash


@pytest.mark.asyncio
async def test_job_posting_auto_hash_and_sink_dedup() -> None:
    sink = InMemoryJobSink()

    job1 = JobPosting(
        source="test_source",
        source_job_id="101",
        source_url="https://example.com/job/101",
        title="Senior Python Engineer",
        company_name="Acme Corp",
        description_text="Building high performance distributed systems.",
        posted_at=datetime.now(timezone.utc),
        attributes={"seniority": "senior", "tech_stack": ["Python", "Docker"]},
    )

    assert job1.content_hash != ""

    # First insert should succeed
    inserted = await sink.save_batch([job1])
    assert inserted == 1
    assert await sink.count() == 1
    assert await sink.contains("test_source", "101") is True

    # Duplicate insert by (source, source_job_id) should be ignored
    inserted_dup = await sink.save_batch([job1])
    assert inserted_dup == 0
    assert await sink.count() == 1

    # Duplicate insert with different ID but identical company + title + description should be ignored
    job2_same_content = JobPosting(
        source="another_source",
        source_job_id="999",
        source_url="https://example.com/job/999",
        title="Senior Python Engineer",
        company_name="Acme Corp",
        description_text="Building high performance distributed systems.",
        posted_at=datetime.now(timezone.utc),
    )
    assert job2_same_content.content_hash == job1.content_hash
    inserted_dup_hash = await sink.save_batch([job2_same_content])
    assert inserted_dup_hash == 0
    assert await sink.count() == 1
    assert await sink.contains("another_source", "999") is True
