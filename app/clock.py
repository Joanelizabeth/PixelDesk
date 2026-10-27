"""Time helpers. All persisted days are local ISO dates (YYYY-MM-DD) and all
timestamps are ISO-8601 strings with an explicit UTC offset."""
from __future__ import annotations

from datetime import date, datetime, timedelta


def now() -> datetime:
    """Timezone-aware local time."""
    return datetime.now().astimezone()


def today() -> date:
    return now().date()


def iso_ts(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.isoformat(timespec="seconds")


def day_of(dt: datetime) -> str:
    """Local calendar day of a timestamp."""
    if dt.tzinfo is not None:
        dt = dt.astimezone()
    return dt.date().isoformat()


def parse_day(value: str) -> date:
    return date.fromisoformat(value)


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


def days_back(end: date, count: int) -> list[date]:
    """`count` consecutive days ending with `end` (oldest first)."""
    return [end - timedelta(days=i) for i in range(count - 1, -1, -1)]


def format_duration(seconds: float, short: bool = False) -> str:
    seconds = int(max(0, round(seconds)))
    hours, rem = divmod(seconds, 3600)
    minutes = rem // 60
    if hours:
        return f"{hours}h {minutes:02d}m" if not short else f"{hours}h{minutes:02d}"
    if minutes:
        return f"{minutes}m"
    return f"{seconds}s" if not short else "0m"


def format_mmss(seconds: float) -> str:
    seconds = int(max(0, round(seconds)))
    minutes, secs = divmod(seconds, 60)
    return f"{minutes:02d}:{secs:02d}"
