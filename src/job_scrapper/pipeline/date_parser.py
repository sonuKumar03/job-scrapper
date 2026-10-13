"""Date parsing and recency filtering utilities."""

from datetime import datetime, timedelta, timezone
import math
from typing import Any
import dateparser


def parse_to_utc(date_input: Any) -> datetime | None:
    """Parse various date formats (relative strings, ISO strings, timestamps) into UTC datetime."""
    if not date_input:
        return None

    try:
        if isinstance(date_input, datetime):
            parsed = date_input
        elif isinstance(date_input, int | float):
            if not math.isfinite(date_input):
                return None
            timestamp = date_input / 1000 if abs(date_input) > 100_000_000_000 else date_input
            parsed = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        elif isinstance(date_input, str):
            stripped = date_input.strip()
            try:
                parsed = datetime.fromisoformat(stripped)
            except ValueError:
                parsed = dateparser.parse(
                    stripped,
                    settings={
                        "TIMEZONE": "UTC",
                        "TO_TIMEZONE": "UTC",
                        "RETURN_AS_TIMEZONE_AWARE": True,
                    },
                )
        else:
            parsed = dateparser.parse(
                str(date_input).strip(),
                settings={
                    "TIMEZONE": "UTC",
                    "TO_TIMEZONE": "UTC",
                    "RETURN_AS_TIMEZONE_AWARE": True,
                },
            )
        if parsed is None:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (OverflowError, OSError, TypeError, ValueError):
        return None


def is_within_days(dt: datetime, max_days: int = 7) -> bool:
    """Check if the given datetime is strictly within the last `max_days` days."""
    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(days=max_days)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return max_days > 0 and cutoff <= dt <= now_utc
