import json
from pathlib import Path

import pytest

from job_scrapper.pipeline.job_metadata import parse_job_metadata


def test_linkedin_closure_requires_top_card_evidence() -> None:
    from job_scrapper.pipeline.job_metadata import parse_linkedin_closure

    fixtures = Path(__file__).parent / 'fixtures' / 'linkedin'
    assert parse_linkedin_closure((fixtures / 'closed.html').read_text()) == 'No longer accepting applications'
    assert parse_linkedin_closure((fixtures / 'normal.html').read_text()) is None
    assert parse_linkedin_closure((fixtures / 'description_only.html').read_text()) is None



def test_job_metadata_handles_json_ld_shapes_and_unrelated_scripts() -> None:
    job = {"@type": "JobPosting", "title": "Software Engineer"}
    typed_job = {**job, "@type": ["Thing", "JobPosting"]}
    for payload, expected in [
        (job, job),
        ([None, {"@type": "Organization"}, job], job),
        ({"@graph": [{"@type": "BreadcrumbList"}, job]}, job),
        ([{"@graph": [typed_job]}], typed_job),
    ]:
        assert parse_job_metadata(["{broken", '{"@type": "WebSite"}', json.dumps(payload)]) == expected
    with pytest.raises(ValueError, match="missing JobPosting metadata"):
        parse_job_metadata(["{broken", "null", '[]', '{"@type": "WebSite"}'])
