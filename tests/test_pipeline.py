from datetime import datetime, timedelta, timezone
from job_scrapper.pipeline.cleaner import clean_html_to_text, normalize_whitespace
from job_scrapper.pipeline.date_parser import is_within_days, parse_to_utc
from job_scrapper.pipeline.hasher import compute_content_hash


def test_clean_html_to_text() -> None:
    html = """
    <div>
        <nav><a href="#">Menu</a></nav>
        <h1>Senior Backend Engineer</h1>
        <p>We are seeking a <strong>Python</strong> specialist.</p>
        <script>console.log("tracking pixel");</script>
        <footer>Footer noise</footer>
    </div>
    """
    clean = clean_html_to_text(html)
    assert "Senior Backend Engineer" in clean
    assert "Python specialist" in clean
    assert "tracking pixel" not in clean
    assert "Menu" not in clean
    from job_scrapper.pipeline.attributes import normalize_attributes
    structured = clean_html_to_text(
        "<h2>Qualifications</h2><ul><li>5+ years building production applications.</li></ul>"
        "<p>Work arrangement: hybrid</p><p>Employment type: contract</p>"
    )
    attributes = normalize_attributes({}, structured)
    assert attributes["experience_years_min"] == 5
    assert attributes["work_arrangement"] == "hybrid"
    assert attributes["employment_type"] == "contract"


def test_date_parser_and_recency_filter() -> None:
    now = datetime.now(timezone.utc)
    recent = now - timedelta(days=2)
    old = now - timedelta(days=14)

    assert is_within_days(recent, max_days=7) is True
    assert is_within_days(old, max_days=7) is False
    assert is_within_days(now + timedelta(seconds=1), max_days=7) is False
    assert parse_to_utc(float("inf")) is None
    assert parse_to_utc(10**100) is None
    assert parse_to_utc("not a date") is None

    # Relative date parsing
    parsed_relative = parse_to_utc("2 days ago")
    assert parsed_relative is not None
    assert is_within_days(parsed_relative, max_days=7) is True


def test_hasher_deterministic() -> None:
    h1 = compute_content_hash("Acme Inc", "Software Engineer", "Building APIs")
    h2 = compute_content_hash("acme inc ", " software engineer", "building apis")
    assert h1 == h2


def test_hasher_uses_full_description() -> None:
    prefix = "x" * 250
    assert compute_content_hash("Acme", "Engineer", prefix + "Python") != compute_content_hash(
        "Acme", "Engineer", prefix + "Kotlin"
    )


def test_attribute_extraction_uses_explicit_unambiguous_evidence() -> None:
    from job_scrapper.pipeline.attributes import normalize_attributes
    result = normalize_attributes({}, "Work arrangement: hybrid\nEmployment type: contract\nRequires 3–5 years of experience.")
    assert result["work_arrangement"] == "hybrid"
    assert result["employment_type"] == "contract"
    assert (result["experience_years_min"], result["experience_years_max"]) == (3, 5)
    assert result["_attribute_evidence"]["experience_years_min"]["method"] == "description"
    assert normalize_attributes(result, "Work arrangement: hybrid\nEmployment type: contract\nRequires 3–5 years of experience.") == result
    assert normalize_attributes({}, "We have 10 years of experience. Remote work benefits. Full time parents welcome.") == {}
    ambiguous = normalize_attributes({}, "Requires 3–5 years of experience or 1–2 years of experience.")
    assert "experience_years_min" not in ambiguous


def test_attribute_normalization_preserves_invalid_values_as_evidence() -> None:
    from job_scrapper.pipeline.attributes import normalize_attributes
    result = normalize_attributes({"employment_type": ["FULL_TIME", "CONTRACT"],
                                   "experience_years_min": True, "experience_years_max": -1,
                                   "work_arrangement": "remote or onsite"}, "")
    assert result["employment_type"] == "unknown"
    assert result["work_arrangement"] == "unknown"
    assert result["experience_years_min"] is None
    assert result["experience_years_max"] is None
    reversed_range = normalize_attributes({"experience_years_min": 5, "experience_years_max": 3}, "")
    assert reversed_range["experience_years_min"] is None
    assert reversed_range["experience_years_max"] is None


def test_experience_requirements_from_captured_qualification_text() -> None:
    from job_scrapper.pipeline.attributes import normalize_attributes
    cases = [
        ("Qualifications\n - 7+ years of software engineering experience building and operating production systems.", 7, None),
        ("What we're looking for\n - 5+ years of experience building production fullstack applications.", 5, None),
        ("Requirements\n - 2+ years in software engineering, data engineering, technical support, DevOps, QA, or a similar role.", 2, None),
        ("Requires 3–5 years of frontend development experience.", 3, 5),
        ("Minimum 3 years in software engineering.", 3, None),
    ]
    for text, low, high in cases:
        result = normalize_attributes({}, text)
        assert result["experience_years_min"] == low
        assert result.get("experience_years_max") == high
        assert result["_attribute_evidence"]["experience_years_min"]["value"] in text
        assert normalize_attributes(result, text) == result
    for text in [
        "Qualifications\n - 5+ years of software engineering experience, 2+ years managing engineering teams.",
        "About us\n - 20 years of software engineering experience serving customers.",
        "Benefits\n - 5 years of experience earns extra vacation.",
        "Qualifications\n - 3–5+ years of B2B sales experience.",
        "Qualifications\n - 5+ years of experience preferred.",
    ]:
        assert "experience_years_min" not in normalize_attributes({}, text)
    structured = normalize_attributes({"experience_years_min": 2}, "Requires 5+ years building production applications.")
    assert structured["experience_years_min"] == 2
