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
