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
YEARS = re.compile(
    r"(?<![\w.\-])(\d+(?:\.\d+)?)(?:\s*[-–—]\s*(\d+(?:\.\d+)?))?"
    r"\s*(\+)?\s*years?\b", re.IGNORECASE,
)
EXPERIENCE = re.compile(
    YEARS.pattern + r"\s+(?:(?:of\s+)?(?:[\w/-]+\s+){0,6}experience\b|"
    r"(?:in|building|developing|managing|leading|working)\b)",
    re.IGNORECASE,
)
QUALIFICATIONS = re.compile(
    r"^(?:qualifications|requirements|what (?:we['’]re looking for|you(?:['’]ll| will) bring)|"
    r"(?:required|minimum) qualifications|what you bring|who you are)\s*:?$", re.IGNORECASE,
)
REQUIRED = re.compile(r"\b(?:requires?|required|minimum(?: of)?|at least|you have|you bring)\b", re.IGNORECASE)


def _experience_requirement(description: str) -> tuple[float, float | None, str] | None:
    """Accept explicit requirements; never collapse differing specialty bounds."""
    in_qualifications = False
    candidates: list[tuple[float, float | None, str]] = []
    for line in description.splitlines():
        text = line.strip().strip("# ")
        if QUALIFICATIONS.fullmatch(text):
            in_qualifications = True
            continue
        if text and not YEARS.search(text) and len(text.split()) <= 8 and not text.startswith(("-", "•")):
            in_qualifications = False
        if not (in_qualifications or REQUIRED.search(text)):
            continue
        matches = list(EXPERIENCE.finditer(text))
        if not matches:
            continue
        if re.search(r"\b(?:preferred|nice[- ]to[- ]have|ideally|optional)\b", text, re.IGNORECASE):
            return None
        mentions = list(YEARS.finditer(text))
        bounds = {(float(m[1]), float(m[2]) if m[2] else None) for m in mentions}
        if len(bounds) != 1 or any(m[2] and m[3] for m in mentions):
            return None
        low, high = bounds.pop()
        if high is not None and low > high:
            return None
        candidates.append((low, high, matches[0][0]))
    if len({(low, high) for low, high, _ in candidates}) == 1:
        return candidates[0]
    return None


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
        requirement = _experience_requirement(description)
        if requirement is not None:
            low, high, text = requirement
            assign(minimum, _years(low), text, "description")
            if high is not None:
                assign(maximum, _years(high), text, "description")
    if evidence:
        result["_attribute_evidence"] = evidence
    return result
