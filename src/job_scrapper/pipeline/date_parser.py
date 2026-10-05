"""Date parsing and recency filtering utilities."""

from datetime import datetime, timedelta, timezone
from typing import Any
import dateparser


def parse_to_utc(date_input: Any) -> datetime | None:
    """Parse various date formats (relative strings, ISO strings, timestamps) into UTC datetime."""
    if not date_input:
        return None

    if isinstance(date_input, datetime):
        if date_input.tzinfo is None:
            return date_input.replace(tzinfo=timezone.utc)
        return date_input.astimezone(timezone.utc)

    # Handle numeric UNIX timestamps (seconds or milliseconds)
    if isinstance(date_input, int | float):
        # If timestamp is likely in milliseconds (greater than year 2100 in seconds)
        if date_input > 4102444800:
            date_input = date_input / 1000.0
        return datetime.fromtimestamp(date_input, tz=timezone.utc)

    # Handle strings
    str_val = str(date_input).strip()
    parsed = dateparser.parse(
        str_val,
        settings={
            "TIMEZONE": "UTC",
            "TO_TIMEZONE": "UTC",
            "RETURN_AS_TIMEZONE_AWARE": True,
        },
    )
    return parsed


def is_within_days(dt: datetime, max_days: int = 7) -> bool:
    """Check if the given datetime is strictly within the last `max_days` days."""
    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(days=max_days)
    # Ensure dt is timezone aware in UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt >= cutoff
