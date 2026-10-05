from datetime import datetime, timezone
import pytest
from job_scrapper.domain.models import JobPosting
from job_scrapper.pipeline.dedup_engine import StandardDeduplicationEngine
from job_scrapper.storage.postgres.models import JobModel
from job_scrapper.storage.postgres.session import DatabaseSessionManager
from job_scrapper.storage.postgres.sink import PostgresJobSink


import uuid

@pytest.mark.asyncio
async def test_end_to_end_dedup_and_enrichment() -> None:
    session_manager = DatabaseSessionManager()
    engine = StandardDeduplicationEngine()
    sink = PostgresJobSink(session_manager, dedup_engine=engine)

    test_uid = uuid.uuid4().hex[:8]

    # Job from Source A (no salary, initial tags)
    job_a = JobPosting(
        source=f"test_source_a_{test_uid}",
        source_job_id=f"job_{test_uid}_a",
        source_url=f"https://source-a.com/job/{test_uid}",
        title="[Remote] Senior Python Engineer",
        company_name=f"Acme Corp {test_uid} Inc.",
        description_text=f"Building distributed high-scale Python microservices {test_uid}.",
        posted_at=datetime.now(timezone.utc),
        attributes={
            "location": "Remote",
            "tech_stack": ["Python", "Docker"],
            "salary_min": None,
            "salary_max": None,
        },
    )

    # Ingest Job A
    inserted_a = await sink.save_batch([job_a])
    assert inserted_a == 1

    # Duplicate Job from Source B (noisy title/company, but adds salary and new tag)
    job_b = JobPosting(
        source=f"test_source_b_{test_uid}",
        source_job_id=f"job_{test_uid}_b",
        source_url=f"https://source-b.com/job/{test_uid}_b",
        title="Sr. Python Engineer (US Only)",
        company_name=f"Acme Corp {test_uid} LLC",
        description_text=f"Building distributed high-scale Python microservices {test_uid}.",
        posted_at=datetime.now(timezone.utc),
        attributes={
            "location": "remote",
            "tech_stack": ["Python", "FastAPI"],
            "salary_min": 150000,
            "salary_max": 190000,
            "currency": "USD",
        },
    )

    # Ingest Job B (should be recognized as duplicate, 0 new jobs inserted)
    inserted_b = await sink.save_batch([job_b])
    assert inserted_b == 0

    # Verify that the canonical job in the database was enriched
    async with session_manager.session() as session:
        from sqlalchemy import select
        sig = engine.compute_canonical_signature(job_a)
        res = await session.execute(select(JobModel).where(JobModel.canonical_signature == sig))
        canonical_record = res.scalar_one()

        assert canonical_record.attributes.get("salary_min") == 150000
        assert canonical_record.attributes.get("salary_max") == 190000
        assert canonical_record.attributes.get("currency") == "USD"
        # Unioned tech stack
        assert "FastAPI" in canonical_record.attributes.get("tech_stack")
        assert "Docker" in canonical_record.attributes.get("tech_stack")

    await session_manager.close()
