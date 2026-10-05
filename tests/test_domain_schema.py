from datetime import datetime, timezone
import pytest
from job_scrapper.domain.models import JobPosting
from job_scrapper.storage.memory import InMemoryJobSink


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
