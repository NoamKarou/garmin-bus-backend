"""Time helpers. Stride stores UTC datetimes; GTFS service dates are Israel-local."""

from __future__ import annotations

import math
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def local_today(now: datetime | None = None) -> date:
    now = now or utc_now()
    return now.astimezone(ISRAEL_TZ).date()


def parse_dt(value: object) -> datetime | None:
    """Parse an ISO-8601 datetime (accepts a trailing 'Z'). Returns aware UTC."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def stride_dt(dt: datetime) -> str:
    """Serialize for a Stride query parameter (httpx will percent-encode '+')."""
    return dt.astimezone(timezone.utc).isoformat()


def minutes_until(arrival: datetime, now: datetime) -> int:
    seconds = (arrival - now).total_seconds()
    return max(0, math.ceil(seconds / 60.0))


def epoch_sec(dt: datetime) -> int:
    """Seconds since the epoch (fits the watch's 32-bit Number until 2038)."""
    return int(dt.timestamp())
