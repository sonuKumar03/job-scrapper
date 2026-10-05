from datetime import datetime, timedelta, timezone
from job_scrapper.domain.models import JobPosting
from job_scrapper.pipeline.dedup_engine import StandardDeduplicationEngine


def test_layer1_normalization() -> None:
    engine = StandardDeduplicationEngine()

    # Company name normalization
    assert engine.normalize_company("Vercel, Inc.") == "vercel"
    assert engine.normalize_company("Vercel LLC") == "vercel"
    assert engine.normalize_company("  Vercel Technologies Ltd. ") == "vercel"

    # Title normalization
    assert engine.normalize_title("[Remote] Sr. Software Engineer (US Only)") == "senior software engineer us only"
    assert engine.normalize_title("Software Engineer (Payments)") == "software engineer payments"
    assert engine.normalize_title("Jr. Developer - Remote") == "junior developer"

    # Canonical signature match across noisy titles/companies
    job1 = JobPosting(
        source="himalayas",
        source_job_id="1",
        source_url="http://a.com",
        title="Sr. Software Engineer",
        company_name="Vercel Inc.",
        description_text="Building fast edge network apps.",
        posted_at=datetime.now(timezone.utc),
        attributes={"location": "Remote"},
    )
    job2 = JobPosting(
        source="jobicy",
        source_job_id="2",
        source_url="http://b.com",
        title="[Remote] Senior Software Engineer",
        company_name="Vercel LLC",
        description_text="Building fast edge network apps.",
        posted_at=datetime.now(timezone.utc),
        attributes={"location": "remote"},
    )
    assert engine.compute_canonical_signature(job1) == engine.compute_canonical_signature(job2)


def test_layer2_simhash_near_duplicates() -> None:
    engine = StandardDeduplicationEngine()

    desc_base = """
    We are looking for a Senior Python Engineer to design, build, and deploy high-throughput microservices.
    Requirements include 5+ years of experience with Python, FastAPI, Docker, and PostgreSQL.
    You will participate in on-call rotations, mentor junior engineers, and optimize database queries.
    Competitive salary and comprehensive healthcare provided.
    """ * 3

    desc_with_footer = desc_base + "\n\nOriginally posted on Himalayas. Apply now!"
    desc_completely_different = """
    Lead Sales Representative needed for outbound enterprise prospecting.
    Must have 7 years experience closing SaaS deals with Fortune 500 executives.
    """

    hash_base = engine.compute_simhash(desc_base)
    hash_footer = engine.compute_simhash(desc_with_footer)
    hash_diff = engine.compute_simhash(desc_completely_different)

    # Near duplicate should have small Hamming distance (<= 3 bits)
    assert engine.are_near_duplicates(hash_base, hash_footer) is True
    # Different job should NOT match
    assert engine.are_near_duplicates(hash_base, hash_diff, max_distance=7) is False


def test_duplicate_matching_requires_content_and_recent_cross_source_identity() -> None:
    engine = StandardDeduplicationEngine()
    now = datetime.now(timezone.utc)
    values = {
        "source": "board-a",
        "source_url": "https://example.com/job/1",
        "title": "Software Engineer",
        "company_name": "Acme",
        "description_text": "Build payments with Python.",
        "posted_at": now,
        "attributes": {"location": "Remote"},
    }
    existing = JobPosting(source_job_id="1", **values)
    unrelated = JobPosting(
        source="board-b",
        source_job_id="2",
        source_url="https://example.com/job/2",
        title="Software Engineer",
        company_name="Acme",
        description_text="Provide payroll support with Kotlin.",
        posted_at=now,
        attributes={"location": "Remote"},
    )
    same_content = existing.model_copy(update={"source": "board-b", "source_job_id": "3"})
    old_repost = same_content.model_copy(update={"posted_at": now - timedelta(days=8)})
    same_source_opening = existing.model_copy(update={"source_job_id": "4"})

    assert engine.compute_canonical_signature(existing) == engine.compute_canonical_signature(unrelated)
    assert engine.is_duplicate(existing, unrelated) is False
    assert engine.is_duplicate(existing, same_content) is True
    assert engine.is_duplicate(existing, old_repost) is False
    assert engine.is_duplicate(existing, same_source_opening) is False


def test_layer3_attribute_enrichment() -> None:
    engine = StandardDeduplicationEngine()

    canonical_attrs = {
        "salary_min": None,
        "salary_max": None,
        "currency": None,
        "tech_stack": ["Python"],
        "location": "Remote",
    }
    duplicate_attrs = {
        "salary_min": 140000,
        "salary_max": 180000,
        "currency": "USD",
        "tech_stack": ["Python", "Docker", "PostgreSQL"],
        "location": "Remote",
    }

    merged, changed = engine.enrich_attributes(canonical_attrs, duplicate_attrs)
    assert changed is True
    assert merged["salary_min"] == 140000
    assert merged["salary_max"] == 180000
    assert merged["currency"] == "USD"
    assert set(merged["tech_stack"]) == {"Python", "Docker", "PostgreSQL"}
