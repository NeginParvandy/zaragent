from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.domain.text import format_jalali_from_gregorian


def local_now(timezone_name: str) -> datetime:
    return datetime.now(tz=ZoneInfo(timezone_name))


def local_jalali_today(timezone_name: str) -> str:
    return format_jalali_from_gregorian(local_now(timezone_name))
