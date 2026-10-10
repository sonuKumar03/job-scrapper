"""Extract a JobPosting object from JSON-LD script contents."""

import json
from collections.abc import Iterable
from typing import Any


def parse_job_metadata(scripts: Iterable[str]) -> dict[str, Any]:
    for script in scripts:
        try:
            pending = [json.loads(script)]
        except json.JSONDecodeError:
            continue
        while pending:
            value = pending.pop()
            if isinstance(value, list):
                pending.extend(reversed(value))
            elif isinstance(value, dict):
                types = value.get("@type")
                if types == "JobPosting" or isinstance(types, list) and "JobPosting" in types:
                    return value
                if "@graph" in value:
                    pending.append(value["@graph"])
    raise ValueError("missing JobPosting metadata")
