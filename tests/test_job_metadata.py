import json

import pytest

from job_scrapper.pipeline.job_metadata import parse_job_metadata


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
