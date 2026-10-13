from datetime import datetime, timezone
from itertools import permutations

from job_scrapper.domain.models import JobPosting
from job_scrapper.storage.memory import InMemoryJobSink


def posting(source: str, source_id: str, **attributes) -> JobPosting:
    return JobPosting(
        source=source, source_job_id=source_id,
        source_url=f"https://example.com/{source_id}",
        title="Engineer", company_name="Acme",
        description_text="Build payments with Python.",
        posted_at=datetime.now(timezone.utc), attributes=attributes,
    )


async def test_distinct_source_ids_survive_every_ingestion_order() -> None:
    for order in permutations([("a", "a1"), ("b", "b1"), ("b", "b2")]):
        for separate_batches in (False, True):
            sink = InMemoryJobSink()
            jobs = [posting(source, source_id) for source, source_id in order]
            batches = [[job] for job in jobs] if separate_batches else [jobs]
            for batch in batches:
                await sink.save_batch(batch)
            assert await sink.count() == 2
            assert sink.jobs_by_id[("b", "b1")] is not sink.jobs_by_id[("b", "b2")]
            assert await sink.contains_many("b", ["b1", "b2"]) == {"b1", "b2"}


async def test_existing_identity_enriches_its_canonical_job() -> None:
    sink = InMemoryJobSink()
    assert await sink.save_batch([posting("a", "a1"), posting("b", "b1")]) == 1
    assert await sink.save_batch([posting("b", "b1", salary_min=100)]) == 0
    assert sink.get_all()[0].attributes == {"salary_min": 100}


async def test_closure_evidence_stays_with_the_primary_posting() -> None:
    sink = InMemoryJobSink()
    primary = posting('a', 'a1')
    duplicate = posting('linkedin', '123456', posting_status='closed',
                        posting_status_evidence='No longer accepting applications',
                        posting_status_checked_at='2026-10-13T00:00:00+00:00')
    assert await sink.save_batch([primary, duplicate]) == 1
    assert 'posting_status' not in sink.get_all()[0].attributes
    sink = InMemoryJobSink()
    assert await sink.save_batch([duplicate, primary]) == 1
    assert sink.get_all()[0].attributes['posting_status'] == 'closed'
