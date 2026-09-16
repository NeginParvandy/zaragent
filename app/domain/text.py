from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

JALALI_DATE_RE = re.compile(r"\b(1[2345]\d{2}[/-]\d{1,2}[/-]\d{1,2})\b")
TIME_RE = re.compile(r"\b([01]?\d|2[0-3])(?::| و |\s)([0-5]\d)(?::([0-5]\d))?\b")


def normalize_persian_text(value: str) -> str:
    text = (value or "").strip()
    table = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩يىك", "01234567890123456789ییک")
    return re.sub(r"\s+", " ", text.translate(table).replace("\u200c", " ")).strip()


def parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    normalized = normalize_persian_text(str(value)).lower()
    if normalized in {"true", "1", "yes", "y", "on", "بله", "بلی"}:
        return True
    if normalized in {"false", "0", "no", "n", "off", "خیر", "نه", ""}:
        return False
    return default


def parse_int(value: Any, default: int | None = None) -> int | None:
    try:
        if value is None or str(value).strip() == "":
            return default
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def parse_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or str(value).strip() == "":
            return default
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _jalali_leap(jy: int) -> bool:
    breaks = [-61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210, 1635, 2060, 2097, 2192, 2262, 2324, 2394, 2456, 3178]
    if jy < breaks[0] or jy >= breaks[-1]:
        return False
    leap_j = -14
    jp = breaks[0]
    jump = 0
    for jm in breaks[1:]:
        jump = jm - jp
        if jy < jm:
            break
        leap_j += (jump // 33) * 8 + ((jump % 33) // 4)
        jp = jm
    n = jy - jp
    leap_j += (n // 33) * 8 + (((n % 33) + 3) // 4)
    if jump % 33 == 4 and jump - n == 4:
        leap_j += 1
    if jump - n < 6:
        n = n - jump + ((jump + 4) // 33) * 33
    leap = ((n + 1) % 33 - 1) % 4
    return leap == 0


def jalali_month_length(year: int, month: int) -> int:
    if month < 1 or month > 12:
        raise ValueError("ماه شمسی نامعتبر است.")
    if month <= 6:
        return 31
    if month <= 11:
        return 30
    return 30 if _jalali_leap(year) else 29


def validate_jalali_date(value: str) -> tuple[int, int, int]:
    normalized = normalize_persian_text(value)
    parts = re.split(r"[/-]", normalized)
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError("فرمت تاریخ شمسی باید YYYY/MM/DD باشد.")
    year, month, day = map(int, parts)
    if year < 1200 or year > 1600:
        raise ValueError("سال شمسی خارج از بازه مجاز است.")
    if month < 1 or month > 12:
        raise ValueError("ماه شمسی نامعتبر است.")
    max_day = jalali_month_length(year, month)
    if day < 1 or day > max_day:
        raise ValueError("روز شمسی برای ماه انتخاب‌شده نامعتبر است.")
    return year, month, day


def normalize_jalali_date(value: str) -> str:
    year, month, day = validate_jalali_date(value)
    return f"{year:04d}/{month:02d}/{day:02d}"


def extract_jalali_dates(text: str) -> list[str]:
    normalized = normalize_persian_text(text)
    return [normalize_jalali_date(match) for match in JALALI_DATE_RE.findall(normalized)]


def validate_jalali_range(start_date: str, end_date: str) -> tuple[str, str]:
    start = normalize_jalali_date(start_date)
    end = normalize_jalali_date(end_date)
    if tuple(map(int, end.split("/"))) < tuple(map(int, start.split("/"))):
        raise ValueError("تاریخ پایان نمی‌تواند قبل از تاریخ شروع باشد.")
    return start, end


def gregorian_to_jalali(year: int, month: int, day: int) -> tuple[int, int, int]:
    """Convert a Gregorian date to Jalali without a third-party runtime dependency."""
    date(year, month, day)  # validates the Gregorian input
    cumulative_days = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if year > 1600:
        jalali_year = 979
        adjusted_year = year - 1600
    else:
        jalali_year = 0
        adjusted_year = year - 621
    adjusted_year_for_leap = adjusted_year + 1 if month > 2 else adjusted_year
    days = (
        365 * adjusted_year
        + (adjusted_year_for_leap + 3) // 4
        - (adjusted_year_for_leap + 99) // 100
        + (adjusted_year_for_leap + 399) // 400
        - 80
        + day
        + cumulative_days[month - 1]
    )
    jalali_year += 33 * (days // 12053)
    days %= 12053
    jalali_year += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jalali_year += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jalali_month = 1 + days // 31
        jalali_day = 1 + days % 31
    else:
        jalali_month = 7 + (days - 186) // 30
        jalali_day = 1 + (days - 186) % 30
    return jalali_year, jalali_month, jalali_day


def format_jalali_from_gregorian(value: date | datetime) -> str:
    year, month, day = gregorian_to_jalali(value.year, value.month, value.day)
    return f"{year:04d}/{month:02d}/{day:02d}"


def is_jalali_month_end(value: str, reminder_days: int = 3) -> bool:
    year, month, day = validate_jalali_date(value)
    threshold = max(1, jalali_month_length(year, month) - max(1, reminder_days) + 1)
    return day >= threshold


def extract_times(text: str) -> list[str]:
    normalized = normalize_persian_text(text)
    return [f"{int(h):02d}:{int(m):02d}:{int(s or 0):02d}" for h, m, s in TIME_RE.findall(normalized)]


def normalize_time(value: str | None) -> str:
    raw = normalize_persian_text(value or "")
    if not raw:
        return ""
    match = TIME_RE.fullmatch(raw) or TIME_RE.search(raw)
    if not match:
        raise ValueError("فرمت ساعت باید HH:MM یا HH:MM:SS باشد.")
    hour, minute, second = match.groups()
    return f"{int(hour):02d}:{int(minute):02d}:{int(second or 0):02d}"


def hours_between(start: str, end: str) -> float:
    start_value = datetime.strptime(normalize_time(start), "%H:%M:%S")
    end_value = datetime.strptime(normalize_time(end), "%H:%M:%S")
    seconds = (end_value - start_value).total_seconds()
    if seconds <= 0:
        raise ValueError("ساعت پایان باید بعد از ساعت شروع باشد.")
    return round(seconds / 3600, 2)


def sap_duration_to_time(value: object) -> str:
    text = str(value or "")
    match = re.fullmatch(r"PT(\d+)H(\d+)M(\d+)S", text)
    if match:
        return f"{int(match.group(1)):02d}:{int(match.group(2)):02d}:{int(match.group(3)):02d}"
    if re.fullmatch(r"\d{6}", text):
        return f"{text[0:2]}:{text[2:4]}:{text[4:6]}"
    try:
        return normalize_time(text)
    except ValueError:
        return ""


def time_to_seconds(value: str | None) -> int | None:
    try:
        hour, minute, second = [int(item) for item in normalize_time(value or "").split(":")]
        return hour * 3600 + minute * 60 + second
    except (ValueError, TypeError):
        return None
