"""Pure attribute normalization; no connector, storage, or model dependencies."""

from copy import deepcopy
import math
import re
from typing import Any

WORK_ARRANGEMENTS = {
    "remote": "remote", "telecommute": "remote", "workfromhome": "remote",
    "hybrid": "hybrid", "onsite": "in-office", "inoffice": "in-office",
}
EMPLOYMENT_TYPES = {
    "fulltime": "full_time", "parttime": "part_time", "contract": "contract",
    "contractor": "contract", "temporary": "temporary", "intern": "internship",
    "internship": "internship", "volunteer": "volunteer", "perdiem": "per_diem",
    "other": "other",
}
EXPERIENCE = re.compile(
    r"\b(?:requires?|required|minimum(?: of)?|at least)\s+"
    r"(\d+(?:\.\d+)?)(?:\s*[-–]\s*(\d+(?:\.\d+)?))?"
    r"\s*(\+)?\s*years?\s+(?:of\s+)?experience\b", re.IGNORECASE,
)


def _label(value: Any, aliases: dict[str, str]) -> str:
    values = value if isinstance(value, list) else [value]
    normalized = {aliases.get(re.sub(r"[\s_-]+", "", item.casefold()), "unknown")
                  if isinstance(item, str) else "unknown" for item in values}
    return next(iter(normalized)) if len(normalized) == 1 else "unknown"


def _years(value: Any) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return int(number) if number.is_integer() else number


def normalize_attributes(attributes: dict[str, Any], description: str = "") -> dict[str, Any]:
    """Normalize explicit source fields, with conservative description fallbacks.

    Unknown custom fields remain intact. Evidence stores original values and the
    normalized value so deduplication can preserve the evidence for each label.
    No seniority, location, salary, or technology inference is performed.
    """
    result = deepcopy(attributes)
    evidence = result.get("_attribute_evidence")
    if not isinstance(evidence, dict):
        evidence = {}
    minimum, maximum = "experience_years_min", "experience_years_max"

    def assign(field: str, value: Any, raw: Any, method: str) -> None:
        result[field] = value
        previous = evidence.get(field)
        if not isinstance(previous, dict) or previous.get("normalized") != value:
            evidence[field] = {"method": method, "value": raw, "normalized": value}

    for field, aliases in (("work_arrangement", WORK_ARRANGEMENTS),
                           ("employment_type", EMPLOYMENT_TYPES)):
        raw = result.get(field)
        if raw not in (None, "", "unknown", []):
            assign(field, _label(raw, aliases), raw, "source")
        elif raw is None or raw in ("", "unknown", []):
            label = "work (?:arrangement|location type)|workplace type" if field == "work_arrangement" else "employment type|job type"
            matches = re.findall(rf"^(?:{label})\s*:\s*([^\n.;]+)", description,
                                 re.IGNORECASE | re.MULTILINE)
            values = {_label(match.strip(), aliases) for match in matches}
            if len(values) == 1 and "unknown" not in values:
                assign(field, values.pop(), matches[0].strip(), "description")

    for field in (minimum, maximum):
        if result.get(field) is not None:
            raw = result[field]
            assign(field, _years(raw), raw, "source")
    low, high = result.get(minimum), result.get(maximum)
    if low is not None and high is not None and low > high:
        for field in (minimum, maximum):
            assign(field, None, attributes[field], "source")
    # Never combine a description range with partial or invalid source bounds.
    if not any(field in attributes for field in (minimum, maximum)):
        matches = list(EXPERIENCE.finditer(description))
        ranges = {(float(m[1]), float(m[2]) if m[2] else None) for m in matches}
        mentions = re.findall(r"(\d+(?:\.\d+)?)(?:\s*[-–]\s*(\d+(?:\.\d+)?))?\s*\+?\s*years?\s+(?:of\s+)?experience\b", description, re.IGNORECASE)
        all_ranges = {(float(low), float(high) if high else None) for low, high in mentions}
        if len(ranges) == 1 and ranges == all_ranges:
            low, high = ranges.pop()
            if high is None or low <= high:
                match = matches[0]
                assign(minimum, _years(low), match[0], "description")
                if high is not None:
                    assign(maximum, _years(high), match[0], "description")
    if evidence:
        result["_attribute_evidence"] = evidence
    return result
