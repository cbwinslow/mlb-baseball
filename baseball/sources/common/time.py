
"""
================================================================================
Time and Date Utilities
Date: 2026-05-09

Shared time handling for all sources.
================================================================================
"""

from datetime import date, datetime, timedelta, timezone
from typing import Optional


def now_utc() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(timezone.utc)


def to_utc(dt: datetime) -> datetime:
    """Convert datetime to UTC.

    Args:
        dt: Datetime (may be naive or aware)

    Returns:
        UTC datetime
    """
    if dt.tzinfo is None:
        # Assume it's already UTC if naive
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def date_range(
    start: date,
    end: date,
) -> list[date]:
    """Generate list of dates in range.

    Args:
        start: Start date (inclusive)
        end: End date (inclusive)

    Returns:
        List of dates
    """
    current = start
    dates = []

    while current <= end:
        dates.append(current)
        current += timedelta(days=1)

    return dates


def season_dates(season: int) -> tuple[date, date]:
    """Get opening and closing dates for MLB season.

    Args:
        season: Season year

    Returns:
        (opening_date, closing_date)
    """
    # MLB seasons typically start late March, end early November
    opening = date(season, 3, 28)  # Approximate
    closing = date(season, 11, 5)   # Approximate

    return opening, closing