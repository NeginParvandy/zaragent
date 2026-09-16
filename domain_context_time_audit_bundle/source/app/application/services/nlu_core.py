from __future__ import annotations

import re
from typing import Any


# ============================================================
# Text normalization
# ============================================================

_CHAR_TRANSLATION = str.maketrans(
    {
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ؤ": "و",
        "إ": "ا",
        "أ": "ا",
        "ۀ": "ه",
        "ة": "ه",
        "‌": " ",
        "‏": "",
        "‎": "",
        "\ufeff": "",
        "۰": "0",
        "۱": "1",
        "۲": "2",
        "۳": "3",
        "۴": "4",
        "۵": "5",
        "۶": "6",
        "۷": "7",
        "۸": "8",
        "۹": "9",
        "٠": "0",
        "١": "1",
        "٢": "2",
        "٣": "3",
        "٤": "4",
        "٥": "5",
        "٦": "6",
        "٧": "7",
        "٨": "8",
        "٩": "9",
    }
)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    text = str(value).translate(_CHAR_TRANSLATION)
    text = text.strip().lower()

    replacements = {
        "پسفردا": "پس فردا",
        "پس فردا": "پس فردا",
        "رزروغذا": "رزرو غذا",
        "رزروکنم": "رزرو کنم",
        "رزروکن": "رزرو کن",
        "ثبتکن": "ثبت کن",
        "لغوکن": "لغو کن",
        "ميخوام": "میخوام",
        "می خواهم": "میخوام",
        "می‌خواهم": "میخوام",
        "می خوام": "میخوام",
        "می‌خوام": "میخوام",
        "مأموريت": "ماموریت",
        "مأموریت": "ماموریت",
        "ماموريت": "ماموریت",
        "استعلاجي": "استعلاجی",
        "استحقاقي": "استحقاقی",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(
        r"\bدهو\s+",
        "ده و ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return text


def _tokens(text: str) -> list[str]:
    return re.findall(
        r"[a-zA-Z]+|[0-9]+|[\u0600-\u06FF]+",
        normalize_text(text),
    )


def _contains_word(
    text: str,
    word: str,
) -> bool:
    return normalize_text(word) in _tokens(text)


def _contains_any_word(
    text: str,
    words: set[str] | tuple[str, ...] | list[str],
) -> bool:
    text_tokens = set(_tokens(text))

    return any(
        normalize_text(word) in text_tokens
        for word in words
    )


def _contains_phrase(
    text: str,
    phrase: str,
) -> bool:
    source_tokens = _tokens(text)
    phrase_tokens = _tokens(phrase)

    if not phrase_tokens:
        return False

    length = len(phrase_tokens)

    for index in range(
        0,
        len(source_tokens) - length + 1,
    ):
        if (
            source_tokens[index:index + length]
            == phrase_tokens
        ):
            return True

    return False


def _contains_any_phrase(
    text: str,
    phrases: list[str] | tuple[str, ...] | set[str],
) -> bool:
    return any(
        _contains_phrase(text, phrase)
        for phrase in phrases
    )


# ============================================================
# Jalali date helpers
# ============================================================

_JALALI_LEAP_REMAINDERS = {
    1,
    5,
    9,
    13,
    17,
    22,
    26,
    30,
}


def _is_jalali_leap(year: int) -> bool:
    return year % 33 in _JALALI_LEAP_REMAINDERS


def _jalali_month_length(
    year: int,
    month: int,
) -> int:
    if 1 <= month <= 6:
        return 31

    if 7 <= month <= 11:
        return 30

    if month == 12:
        return 30 if _is_jalali_leap(year) else 29

    raise ValueError("Invalid Jalali month.")


def _parse_jalali_date(
    value: str,
) -> tuple[int, int, int] | None:
    normalized = normalize_text(value)

    match = re.fullmatch(
        r"\s*(1[34][0-9]{2})[/-]"
        r"([0-9]{1,2})[/-]"
        r"([0-9]{1,2})\s*",
        normalized,
    )

    if not match:
        return None

    year = int(match.group(1))
    month = int(match.group(2))
    day = int(match.group(3))

    if not 1 <= month <= 12:
        return None

    try:
        max_day = _jalali_month_length(
            year,
            month,
        )
    except ValueError:
        return None

    if not 1 <= day <= max_day:
        return None

    return year, month, day


def _format_jalali_date(
    year: int,
    month: int,
    day: int,
) -> str:
    return f"{year:04d}/{month:02d}/{day:02d}"


def _add_jalali_days(
    value: str,
    days: int,
) -> str:
    parsed = _parse_jalali_date(value)

    if parsed is None:
        return value

    year, month, day = parsed

    if days > 0:
        for _ in range(days):
            day += 1

            max_day = _jalali_month_length(
                year,
                month,
            )

            if day > max_day:
                day = 1
                month += 1

                if month > 12:
                    month = 1
                    year += 1

    elif days < 0:
        for _ in range(abs(days)):
            day -= 1

            if day < 1:
                month -= 1

                if month < 1:
                    month = 12
                    year -= 1

                day = _jalali_month_length(
                    year,
                    month,
                )

    return _format_jalali_date(
        year,
        month,
        day,
    )


_JALALI_MONTH_NAMES = {
    "فروردین": 1,
    "اردیبهشت": 2,
    "خرداد": 3,
    "تیر": 4,
    "مرداد": 5,
    "شهریور": 6,
    "مهر": 7,
    "آبان": 8,
    "اذر": 9,
    "آذر": 9,
    "دی": 10,
    "بهمن": 11,
    "اسفند": 12,
}

_PERSIAN_DAY_WORDS = {
    "یک": 1,
    "اول": 1,
    "یکم": 1,
    "دو": 2,
    "دوم": 2,
    "سه": 3,
    "سوم": 3,
    "چهار": 4,
    "چهارم": 4,
    "پنج": 5,
    "پنجم": 5,
    "شش": 6,
    "ششم": 6,
    "هفت": 7,
    "هفتم": 7,
    "هشت": 8,
    "هشتم": 8,
    "نه": 9,
    "نهم": 9,
    "ده": 10,
    "دهم": 10,
    "یازده": 11,
    "یازدهم": 11,
    "دوازده": 12,
    "دوازدهم": 12,
    "سیزده": 13,
    "سیزدهم": 13,
    "چهارده": 14,
    "چهاردهم": 14,
    "پانزده": 15,
    "پانزدهم": 15,
    "شانزده": 16,
    "شانزدهم": 16,
    "هفده": 17,
    "هفدهم": 17,
    "هجده": 18,
    "هجدهم": 18,
    "نوزده": 19,
    "نوزدهم": 19,
    "بیست": 20,
    "بیستم": 20,
    "بیست و یک": 21,
    "بیست و یکم": 21,
    "بیست و دو": 22,
    "بیست و دوم": 22,
    "بیست و سه": 23,
    "بیست و سوم": 23,
    "بیست و چهار": 24,
    "بیست و چهارم": 24,
    "بیست و پنج": 25,
    "بیست و پنجم": 25,
    "بیست و شش": 26,
    "بیست و ششم": 26,
    "بیست و هفت": 27,
    "بیست و هفتم": 27,
    "بیست و هشت": 28,
    "بیست و هشتم": 28,
    "بیست و نه": 29,
    "بیست و نهم": 29,
    "سی": 30,
    "سی ام": 30,
    "سیام": 30,
    "سی و یک": 31,
    "سی و یکم": 31,
}

_MONTH_NAME_PATTERN = "|".join(
    re.escape(value)
    for value in sorted(
        _JALALI_MONTH_NAMES,
        key=len,
        reverse=True,
    )
)

_DAY_WORD_PATTERN = "|".join(
    re.escape(value)
    for value in sorted(
        _PERSIAN_DAY_WORDS,
        key=len,
        reverse=True,
    )
)

_DAY_VALUE_PATTERN = (
    rf"(?:[0-9]{{1,2}}|{_DAY_WORD_PATTERN})"
)


def _parse_jalali_day(value: str) -> int | None:
    normalized = normalize_text(value)
    normalized = re.sub(
        r"\s+",
        " ",
        normalized,
    ).strip()

    normalized = re.sub(
        r"^([0-9]{1,2})\s*(?:ام|مین)$",
        r"\1",
        normalized,
    )

    if normalized.isdigit():
        day = int(normalized)
        return day if 1 <= day <= 31 else None

    return _PERSIAN_DAY_WORDS.get(normalized)


def _resolve_named_date_year(
    text: str,
    reference_date: str,
) -> int | None:
    normalized = normalize_text(text)

    explicit_year_match = re.search(
        r"(?<![0-9])(1[34][0-9]{2})(?![0-9])",
        normalized,
    )

    if explicit_year_match:
        return int(explicit_year_match.group(1))

    parsed_reference = _parse_jalali_date(
        reference_date
    )

    if parsed_reference is None:
        return None

    reference_year = parsed_reference[0]

    if _contains_any_phrase(
        normalized,
        {
            "سال بعد",
            "سال آینده",
            "سال اینده",
        },
    ):
        return reference_year + 1

    if _contains_any_phrase(
        normalized,
        {
            "سال قبل",
            "سال گذشته",
            "سال پیش",
        },
    ):
        return reference_year - 1

    return reference_year


def _extract_named_jalali_date(
    text: str,
    reference_date: str,
) -> str | None:
    normalized = normalize_text(text)

    patterns = (
        # Examples: 9 مرداد / نهم مرداد / روز 9 مرداد ماه
        rf"(?:\bروز\s+)?"
        rf"(?P<day>{_DAY_VALUE_PATTERN})"
        rf"(?:\s*(?:ام|مین))?"
        rf"\s+"
        rf"(?P<month>{_MONTH_NAME_PATTERN})"
        rf"(?:\s*ماه)?",

        # Examples: مرداد 9 / مرداد ماه نهم
        rf"(?P<month>{_MONTH_NAME_PATTERN})"
        rf"(?:\s*ماه)?"
        rf"\s+"
        rf"(?:روز\s+)?"
        rf"(?P<day>{_DAY_VALUE_PATTERN})"
        rf"(?:\s*(?:ام|مین))?",
    )

    for pattern in patterns:
        match = re.search(
            pattern,
            normalized,
        )

        if not match:
            continue

        day = _parse_jalali_day(
            match.group("day")
        )

        month_name = normalize_text(
            match.group("month")
        )
        month = _JALALI_MONTH_NAMES.get(
            month_name
        )
        year = _resolve_named_date_year(
            normalized,
            reference_date,
        )

        if (
            day is None
            or month is None
            or year is None
        ):
            continue

        candidate = _format_jalali_date(
            year,
            month,
            day,
        )

        parsed = _parse_jalali_date(candidate)

        if parsed is not None:
            return _format_jalali_date(*parsed)

    return None


def _extract_explicit_jalali_date(
    text: str,
    reference_date: str,
) -> str | None:
    normalized = normalize_text(text)

    matches = re.findall(
        r"(?<![0-9])"
        r"(1[34][0-9]{2})[/-]"
        r"([0-9]{1,2})[/-]"
        r"([0-9]{1,2})"
        r"(?![0-9])",
        normalized,
    )

    for year_text, month_text, day_text in matches:
        candidate = (
            f"{year_text}/"
            f"{month_text}/"
            f"{day_text}"
        )

        parsed = _parse_jalali_date(candidate)

        if parsed is not None:
            return _format_jalali_date(*parsed)

    return _extract_named_jalali_date(
        normalized,
        reference_date,
    )


def _extract_relative_date(
    text: str,
    reference_date: str,
) -> str | None:
    normalized = normalize_text(text)

    if _contains_phrase(
        normalized,
        "پس فردا",
    ):
        return _add_jalali_days(
            reference_date,
            2,
        )

    if _contains_word(
        normalized,
        "فردا",
    ):
        return _add_jalali_days(
            reference_date,
            1,
        )

    if _contains_word(
        normalized,
        "امروز",
    ):
        return reference_date

    if _contains_word(
        normalized,
        "دیروز",
    ):
        return _add_jalali_days(
            reference_date,
            -1,
        )

    return None


def _extract_date(
    text: str,
    reference_date: str,
) -> str | None:
    explicit_date = (
        _extract_explicit_jalali_date(
            text,
            reference_date,
        )
    )

    if explicit_date:
        return explicit_date

    return _extract_relative_date(
        text,
        reference_date,
    )


# ============================================================
# Persian number parsing
# ============================================================

_BASE_NUMBER_WORDS = {
    "صفر": 0,
    "یک": 1,
    "دو": 2,
    "سه": 3,
    "چهار": 4,
    "پنج": 5,
    "شش": 6,
    "هفت": 7,
    "هشت": 8,
    "نه": 9,
    "ده": 10,
    "یازده": 11,
    "دوازده": 12,
    "سیزده": 13,
    "چهارده": 14,
    "پانزده": 15,
    "شانزده": 16,
    "هفده": 17,
    "هجده": 18,
    "نوزده": 19,
    "بیست": 20,
    "سی": 30,
    "چهل": 40,
    "پنجاه": 50,
    "شصت": 60,
    "هفتاد": 70,
    "هشتاد": 80,
    "نود": 90,
}

_UNITS = {
    1: "یک",
    2: "دو",
    3: "سه",
    4: "چهار",
    5: "پنج",
    6: "شش",
    7: "هفت",
    8: "هشت",
    9: "نه",
}

_TENS = {
    20: "بیست",
    30: "سی",
    40: "چهل",
    50: "پنجاه",
    60: "شصت",
    70: "هفتاد",
    80: "هشتاد",
    90: "نود",
}


def _build_number_phrases(
    maximum: int,
) -> dict[str, int]:
    result: dict[str, int] = {}

    for word, number in _BASE_NUMBER_WORDS.items():
        if number <= maximum:
            result[word] = number

    for tens_number, tens_word in _TENS.items():
        if tens_number > maximum:
            continue

        result[tens_word] = tens_number

        for unit_number, unit_word in _UNITS.items():
            value = tens_number + unit_number

            if value <= maximum:
                result[
                    f"{tens_word} و {unit_word}"
                ] = value

    return result


_HOUR_PHRASES = _build_number_phrases(24)
_MINUTE_PHRASES = _build_number_phrases(59)

_HOUR_PATTERN = "|".join(
    re.escape(value)
    for value in sorted(
        _HOUR_PHRASES,
        key=len,
        reverse=True,
    )
)

_MINUTE_PATTERN = "|".join(
    re.escape(value)
    for value in sorted(
        _MINUTE_PHRASES,
        key=len,
        reverse=True,
    )
)

_HOUR_VALUE_PATTERN = (
    rf"(?:[0-9]{{1,2}}|{_HOUR_PATTERN})"
)

_MINUTE_VALUE_PATTERN = (
    rf"(?:[0-9]{{1,2}}|{_MINUTE_PATTERN})"
)


def _parse_number_value(
    value: str,
    *,
    maximum: int,
) -> int | None:
    normalized = normalize_text(value)
    normalized = re.sub(
        r"\s+",
        " ",
        normalized,
    ).strip()

    if normalized.isdigit():
        number = int(normalized)

        if 0 <= number <= maximum:
            return number

        return None

    phrase_map = (
        _HOUR_PHRASES
        if maximum <= 24
        else _MINUTE_PHRASES
    )

    number = phrase_map.get(normalized)

    if number is None:
        return None

    if not 0 <= number <= maximum:
        return None

    return number


# ============================================================
# Time extraction
# ============================================================

_MERIDIEM_WORDS = {
    "صبح": "AM",
    "بامداد": "AM",
    "ظهر": "PM",
    "بعدازظهر": "PM",
    "عصر": "PM",
    "شب": "PM",
}


def _extract_meridiem(
    text: str,
) -> str | None:
    normalized = normalize_text(text)

    for word, value in _MERIDIEM_WORDS.items():
        if _contains_word(normalized, word):
            return value

    return None


def _apply_meridiem(
    hour: int,
    meridiem: str | None,
) -> int:
    if meridiem == "AM":
        if hour == 12:
            return 0

        return hour

    if meridiem == "PM":
        if 1 <= hour <= 11:
            return hour + 12

        return hour

    return hour


def _format_time(
    hour: int,
    minute: int,
) -> str:
    return f"{hour:02d}:{minute:02d}"


def _time_result(
    *,
    time_value: str | None = None,
    found: bool = False,
    ambiguous: bool = False,
    error: str | None = None,
    hour: int | None = None,
    minute: int | None = None,
    meridiem: str | None = None,
) -> dict[str, Any]:
    return {
        "time": time_value,
        "found": found,
        "ambiguous": ambiguous,
        "error": error,
        "hour": hour,
        "minute": minute,
        "meridiem": meridiem,
    }


def _parse_time_segment(
    segment: str,
) -> dict[str, Any]:
    text = normalize_text(segment)
    meridiem = _extract_meridiem(text)

    # --------------------------------------------------------
    # HH:MM
    # --------------------------------------------------------

    colon_match = re.search(
        r"(?<![0-9/])"
        r"([0-9]{1,2}):([0-9]{1,2})"
        r"(?![0-9])",
        text,
    )

    if colon_match:
        hour = int(colon_match.group(1))
        minute = int(colon_match.group(2))

        if not 0 <= hour <= 23:
            return _time_result(
                found=True,
                error="ساعت واردشده معتبر نیست.",
            )

        if not 0 <= minute <= 59:
            return _time_result(
                found=True,
                error=(
                    "دقیقه باید عددی بین "
                    "۰ تا ۵۹ باشد."
                ),
            )

        hour = _apply_meridiem(
            hour,
            meridiem,
        )

        return _time_result(
            time_value=_format_time(
                hour,
                minute,
            ),
            found=True,
        )

    # --------------------------------------------------------
    # Three quarters
    # --------------------------------------------------------

    three_quarter_match = re.search(
        rf"(?:ساعت\s+)?"
        rf"(?P<hour>{_HOUR_VALUE_PATTERN})"
        rf"\s+و\s+سه\s+ربع",
        text,
    )

    if three_quarter_match:
        hour = _parse_number_value(
            three_quarter_match.group("hour"),
            maximum=24,
        )

        if hour is None or not 0 <= hour <= 23:
            return _time_result(
                found=True,
                error="ساعت واردشده معتبر نیست.",
            )

        hour = _apply_meridiem(
            hour,
            meridiem,
        )

        return _time_result(
            time_value=_format_time(
                hour,
                45,
            ),
            found=True,
        )

    # --------------------------------------------------------
    # Half
    # --------------------------------------------------------

    half_match = re.search(
        rf"(?:ساعت\s+)?"
        rf"(?P<hour>{_HOUR_VALUE_PATTERN})"
        rf"\s+و\s+نیم",
        text,
    )

    if half_match:
        hour = _parse_number_value(
            half_match.group("hour"),
            maximum=24,
        )

        if hour is None or not 0 <= hour <= 23:
            return _time_result(
                found=True,
                error="ساعت واردشده معتبر نیست.",
            )

        hour = _apply_meridiem(
            hour,
            meridiem,
        )

        return _time_result(
            time_value=_format_time(
                hour,
                30,
            ),
            found=True,
        )

    # --------------------------------------------------------
    # Quarter
    # --------------------------------------------------------

    quarter_match = re.search(
        rf"(?:ساعت\s+)?"
        rf"(?P<hour>{_HOUR_VALUE_PATTERN})"
        rf"\s+و\s+ربع",
        text,
    )

    if quarter_match:
        hour = _parse_number_value(
            quarter_match.group("hour"),
            maximum=24,
        )

        if hour is None or not 0 <= hour <= 23:
            return _time_result(
                found=True,
                error="ساعت واردشده معتبر نیست.",
            )

        hour = _apply_meridiem(
            hour,
            meridiem,
        )

        return _time_result(
            time_value=_format_time(
                hour,
                15,
            ),
            found=True,
        )

    # --------------------------------------------------------
    # Hour and minute: 10 و 50 / ده و پنجاه
    # --------------------------------------------------------

    hour_minute_match = re.search(
        rf"(?:ساعت\s+)?"
        rf"(?P<hour>{_HOUR_VALUE_PATTERN})"
        rf"\s+و\s+"
        rf"(?P<minute>{_MINUTE_VALUE_PATTERN})"
        rf"(?:\s+دقیقه)?",
        text,
    )

    if hour_minute_match:
        hour = _parse_number_value(
            hour_minute_match.group("hour"),
            maximum=24,
        )

        minute_text = (
            hour_minute_match.group("minute")
        )

        minute = _parse_number_value(
            minute_text,
            maximum=99,
        )

        if minute is None:
            raw_minute = normalize_text(
                minute_text
            )

            if raw_minute.isdigit():
                minute = int(raw_minute)

        if hour is None or not 0 <= hour <= 23:
            return _time_result(
                found=True,
                error="ساعت واردشده معتبر نیست.",
            )

        if minute is None or not 0 <= minute <= 59:
            return _time_result(
                found=True,
                error=(
                    "دقیقه باید عددی بین "
                    "۰ تا ۵۹ باشد."
                ),
            )

        hour = _apply_meridiem(
            hour,
            meridiem,
        )

        return _time_result(
            time_value=_format_time(
                hour,
                minute,
            ),
            found=True,
        )

    # --------------------------------------------------------
    # Invalid written minute such as 75
    # --------------------------------------------------------

    invalid_minute_match = re.search(
        rf"(?:ساعت\s+)?"
        rf"(?P<hour>{_HOUR_VALUE_PATTERN})"
        rf"\s+و\s+"
        rf"(?P<minute>[0-9]{{1,3}}|"
        rf"هفتاد(?:\s+و\s+\S+)?|"
        rf"هشتاد(?:\s+و\s+\S+)?|"
        rf"نود(?:\s+و\s+\S+)?)"
        rf"\s+دقیقه",
        text,
    )

    if invalid_minute_match:
        return _time_result(
            found=True,
            error=(
                "دقیقه باید عددی بین "
                "۰ تا ۵۹ باشد."
            ),
        )

    # --------------------------------------------------------
    # Plain hour
    # --------------------------------------------------------

    if meridiem is not None:
        meridiem_pattern = (
            r"صبح|بامداد|ظهر|بعدازظهر|عصر|شب"
        )

        plain_hour_match = re.search(
            rf"(?:ساعت\s+)?"
            rf"(?P<hour>{_HOUR_VALUE_PATTERN})"
            rf"\s+(?:{meridiem_pattern})",
            text,
        )
    else:
        plain_hour_match = re.search(
            rf"(?:ساعت\s+)"
            rf"(?P<hour>{_HOUR_VALUE_PATTERN})",
            text,
        )

    if plain_hour_match:
        hour = _parse_number_value(
            plain_hour_match.group("hour"),
            maximum=24,
        )

        if hour is None or not 0 <= hour <= 23:
            return _time_result(
                found=True,
                error="ساعت واردشده معتبر نیست.",
            )

        if (
            meridiem is None
            and 1 <= hour <= 12
        ):
            return _time_result(
                found=True,
                ambiguous=True,
                hour=hour,
                minute=0,
            )

        hour = _apply_meridiem(
            hour,
            meridiem,
        )

        return _time_result(
            time_value=_format_time(
                hour,
                0,
            ),
            found=True,
        )

    return _time_result()


def _extract_time_entities(
    text: str,
) -> dict[str, Any]:
    normalized = normalize_text(text)
    meridiem = _extract_meridiem(
        normalized
    )

    range_match = re.search(
        r"\bاز\b(?P<start>.+?)"
        r"\bتا\b(?P<end>.+)",
        normalized,
    )

    if range_match:
        start_result = _parse_time_segment(
            range_match.group("start")
        )

        end_result = _parse_time_segment(
            range_match.group("end")
        )

        errors = [
            result["error"]
            for result in (
                start_result,
                end_result,
            )
            if result.get("error")
        ]

        return {
            "isRange": True,
            "startTime": start_result.get(
                "time"
            ),
            "endTime": end_result.get(
                "time"
            ),
            "startAmbiguous": bool(
                start_result.get("ambiguous")
            ),
            "endAmbiguous": bool(
                end_result.get("ambiguous")
            ),
            "startHour": start_result.get(
                "hour"
            ),
            "startMinute": (
                start_result.get("minute")
            ),
            "endHour": end_result.get(
                "hour"
            ),
            "endMinute": end_result.get(
                "minute"
            ),
            "meridiem": meridiem,
            "errors": errors,
        }

    single_result = _parse_time_segment(
        normalized
    )

    errors = []

    if single_result.get("error"):
        errors.append(
            single_result["error"]
        )

    return {
        "isRange": False,
        "time": single_result.get("time"),
        "ambiguous": bool(
            single_result.get("ambiguous")
        ),
        "hour": single_result.get("hour"),
        "minute": single_result.get("minute"),
        "meridiem": meridiem,
        "found": bool(
            single_result.get("found")
        ),
        "errors": errors,
    }


# ============================================================
# Intent detection
# ============================================================

_CONFIRM_PHRASES = {
    "بله",
    "آره",
    "اره",
    "تایید",
    "تأیید",
    "تایید میکنم",
    "تأیید میکنم",
    "انجام بده",
    "اوکی",
    "ok",
    "yes",
}

_REJECT_PHRASES = {
    "نه",
    "خیر",
    "نه ممنون",
    "خیر ممنون",
    "no",
}

_CANCEL_CONVERSATION_PHRASES = {
    "لغو",
    "لغو کن",
    "حذف",
    "حذف کن",
    "کنسل",
    "کنسل کن",
    "بیخیال",
    "بی خیال",
    "انصراف",
    "منصرف شدم",
    "نمیخوام",
    "نمی خواهم",
    "cancel",
}

_FOOD_WORDS = {
    "غذا",
    "غذای",
    "ناهار",
    "منو",
    "رستوران",
}

_RESERVE_WORDS = {
    "رزرو",
    "بگیر",
    "بگیرم",
    "بگیری",
    "ثبت",
    "میخوام",
    "میخواهم",
}

_CANCEL_WORDS = {
    "لغو",
    "حذف",
    "کنسل",
}

_SHOW_WORDS = {
    "نمایش",
    "نشان",
    "بگو",
    "ببینم",
    "چیه",
    "چیست",
    "داریم",
}

_CREATE_WORDS = {
    "ثبت",
    "ایجاد",
    "درخواست",
    "بزن",
    "میخوام",
    "میخواهم",
}

_OUT_OF_SCOPE_WORDS = {
    "دلار",
    "طلا",
    "بورس",
    "ارز",
    "بیتکوین",
    "هواشناسی",
    "فوتبال",
    "خبر",
}


def _detect_food_intent(
    text: str,
) -> tuple[str, str] | None:
    # FOOD_RECOMMENDATION_V3
    has_food_word = _contains_any_word(
        text,
        _FOOD_WORDS,
    )

    has_reserve_word = _contains_any_word(
        text,
        _RESERVE_WORDS,
    )

    has_cancel_word = _contains_any_word(
        text,
        _CANCEL_WORDS,
    )

    has_reservation_word = (
        _contains_word(
            text,
            "رزرو",
        )
        or _contains_word(
            text,
            "رزروها",
        )
        or _contains_word(
            text,
            "رزروهای",
        )
    )

    has_order_word = (
        _contains_word(
            text,
            "سفارش",
        )
    )

    reserve_command_words = {
        "کن",
        "کنم",
        "بده",
        "بگیر",
        "بگیرم",
        "بگیری",
        "شه",
        "شود",
    }

    if (
        has_cancel_word
        and (
            has_food_word
            or has_reservation_word
        )
    ):
        return (
            "FOOD",
            "CANCEL_FOOD",
        )

    reservation_status_phrases = {
        "چی رزرو کردم",
        "چه چیزی رزرو کردم",
        "چی برام رزرو شده",
        "رزرو من",
        "رزرو شده",
        "غذای رزرو شده",
    }

    if _contains_any_phrase(
        text,
        reservation_status_phrases,
    ):
        return (
            "FOOD",
            "SHOW_FOOD_RESERVATION",
        )

    register_food_phrases = {
        "ثبت غذا",
        "غذا ثبت شه",
        "غذا ثبت شود",
        "غذا رو ثبت کن",
        "غذا را ثبت کن",
        "غذا انتخاب شه",
        "غذا انتخاب شود",
        "غذا رو انتخاب کن",
        "غذا را انتخاب کن",
        "برام غذا بگیر",
        "برایم غذا بگیر",
    }

    if (
        (
            (
                has_reservation_word
                or has_order_word
            )
            and _contains_any_word(
                text,
                reserve_command_words,
            )
        )
        or (
            has_food_word
            and has_reserve_word
        )
        or _contains_any_phrase(
            text,
            register_food_phrases,
        )
    ):
        return (
            "FOOD",
            "RESERVE_FOOD",
        )

    menu_phrases = {
        "چه غذایی",
        "چه غذا",
        "چی داریم",
        "ناهارهای این هفته",
        "منوی غذا",
        "غذا رو نشون بده",
        "غذا را نشان بده",
        "غذای امروز رو نشون بده",
        "غذای فردا رو نشون بده",
    }

    show_words = set(
        _SHOW_WORDS
    ) | {
        "نشون",
        "ببین",
        "بیار",
    }

    if (
        _contains_word(
            text,
            "منو",
        )
        or (
            has_food_word
            and (
                _contains_any_word(
                    text,
                    show_words,
                )
                or _contains_any_phrase(
                    text,
                    menu_phrases,
                )
            )
        )
    ):
        return (
            "FOOD",
            "SHOW_FOOD_MENU",
        )

    if has_food_word:
        return (
            "FOOD",
            "FOOD_UNKNOWN",
        )

    return None


def _detect_leave_intent(
    text: str,
) -> tuple[str, str] | None:
    if not _contains_word(
        text,
        "مرخصی",
    ):
        return None

    balance_words = {
        "مانده",
        "باقی",
        "باقیمانده",
        "موجودی",
        "حساب",
        "چقدر",
        "دارم",
        "مونده",
        "ماندهام",
    }

    balance_phrases = [
        "چند ساعت مرخصی",
        "چند روز مرخصی",
        "وضعیت حساب مرخصی",
        "مرخصی باقی مونده",
        "مانده مرخصی",
    ]

    if (
        _contains_any_word(
            text,
            balance_words,
        )
        or _contains_any_phrase(
            text,
            balance_phrases,
        )
    ):
        return (
            "LEAVE",
            "GET_LEAVE_BALANCE",
        )

    if _contains_any_word(
        text,
        _CANCEL_WORDS,
    ):
        return (
            "LEAVE",
            "CANCEL_LEAVE",
        )

    if _contains_any_word(
        text,
        _CREATE_WORDS,
    ):
        return (
            "LEAVE",
            "CREATE_LEAVE",
        )

    if _contains_any_word(
        text,
        _SHOW_WORDS,
    ):
        return (
            "LEAVE",
            "SHOW_LEAVE_REQUESTS",
        )

    return "LEAVE", "LEAVE_UNKNOWN"


def _detect_mission_intent(
    text: str,
) -> tuple[str, str] | None:
    if not _contains_word(
        text,
        "ماموریت",
    ):
        return None

    if _contains_any_word(
        text,
        _CANCEL_WORDS,
    ):
        return (
            "MISSION",
            "CANCEL_MISSION",
        )

    if _contains_any_word(
        text,
        _CREATE_WORDS,
    ):
        return (
            "MISSION",
            "CREATE_MISSION",
        )

    if _contains_any_word(
        text,
        _SHOW_WORDS,
    ):
        return (
            "MISSION",
            "SHOW_MISSIONS",
        )

    return "MISSION", "MISSION_UNKNOWN"


def _detect_attendance_intent(
    text: str,
    time_entities: dict[str, Any],
) -> tuple[str, str] | None:
    attendance_words = {
        "تردد",
        "ورود",
        "خروج",
        "ساعتزنی",
    }

    if not _contains_any_word(
        text,
        attendance_words,
    ):
        return None

    show_phrases = [
        "نشان بده",
        "نمایش بده",
        "تردد من",
        "سوابق تردد",
        "گزارش تردد",
    ]

    if _contains_any_phrase(
        text,
        show_phrases,
    ):
        return (
            "ATTENDANCE",
            "SHOW_ATTENDANCE",
        )

    if (
        time_entities.get("isRange")
        and (
            time_entities.get("startTime")
            or time_entities.get("endTime")
        )
    ):
        return (
            "ATTENDANCE",
            "CREATE_TIME_EVENT_RANGE",
        )

    if (
        _contains_any_word(
            text,
            _CREATE_WORDS,
        )
        or _contains_word(text, "ورود")
        or _contains_word(text, "خروج")
    ):
        return (
            "ATTENDANCE",
            "CREATE_TIME_EVENT",
        )

    return (
        "ATTENDANCE",
        "SHOW_ATTENDANCE",
    )


def _detect_domain_intent(
    text: str,
    time_entities: dict[str, Any],
) -> tuple[str, str]:
    food_result = _detect_food_intent(
        text
    )

    if food_result:
        return food_result

    leave_result = _detect_leave_intent(
        text
    )

    if leave_result:
        return leave_result

    mission_result = _detect_mission_intent(
        text
    )

    if mission_result:
        return mission_result

    attendance_result = (
        _detect_attendance_intent(
            text,
            time_entities,
        )
    )

    if attendance_result:
        return attendance_result

    if _contains_any_word(
        text,
        _OUT_OF_SCOPE_WORDS,
    ):
        return (
            "OUT_OF_SCOPE",
            "UNSUPPORTED",
        )

    if _contains_any_word(
        text,
        _CREATE_WORDS,
    ):
        return (
            "UNKNOWN",
            "NEEDS_DOMAIN",
        )

    return (
        "OUT_OF_SCOPE",
        "UNSUPPORTED",
    )


# ============================================================
# Entities, missing fields and guidance
# ============================================================

def _extract_event_type(
    text: str,
) -> str | None:
    has_entry = _contains_word(
        text,
        "ورود",
    )

    has_exit = _contains_word(
        text,
        "خروج",
    )

    if has_entry and not has_exit:
        return "ENTRY"

    if has_exit and not has_entry:
        return "EXIT"

    return None


def _build_entities(
    *,
    text: str,
    domain: str,
    intent: str,
    reference_date: str,
    previous_entities: dict[str, Any],
    time_entities: dict[str, Any],
) -> dict[str, Any]:
    entities = dict(previous_entities)

    detected_date = _extract_date(
        text,
        reference_date,
    )

    if detected_date:
        entities["date"] = detected_date

    if _contains_phrase(
        text,
        "این هفته",
    ):
        entities["dateScope"] = (
            "CURRENT_WEEK"
        )

    if _contains_phrase(
        text,
        "هفته بعد",
    ):
        entities["dateScope"] = (
            "NEXT_WEEK"
        )

    if domain in {
        "LEAVE",
        "MISSION",
    }:
        if detected_date:
            entities["startDate"] = (
                detected_date
            )
            entities["endDate"] = (
                detected_date
            )

    if domain == "ATTENDANCE":
        event_type = _extract_event_type(
            text
        )

        if event_type:
            entities["eventType"] = (
                event_type
            )

        meridiem = time_entities.get(
            "meridiem"
        )

        if time_entities.get("isRange"):
            start_time = time_entities.get(
                "startTime"
            )
            end_time = time_entities.get(
                "endTime"
            )

            if start_time:
                entities["startTime"] = (
                    start_time
                )
                entities.pop(
                    "ambiguousStartHour",
                    None,
                )
                entities.pop(
                    "ambiguousStartMinute",
                    None,
                )

            elif (
                time_entities.get(
                    "startAmbiguous"
                )
                and time_entities.get(
                    "startHour"
                )
                is not None
            ):
                entities[
                    "ambiguousStartHour"
                ] = int(
                    time_entities["startHour"]
                )
                entities[
                    "ambiguousStartMinute"
                ] = int(
                    time_entities.get(
                        "startMinute"
                    )
                    or 0
                )

            if end_time:
                entities["endTime"] = (
                    end_time
                )
                entities.pop(
                    "ambiguousEndHour",
                    None,
                )
                entities.pop(
                    "ambiguousEndMinute",
                    None,
                )

            elif (
                time_entities.get(
                    "endAmbiguous"
                )
                and time_entities.get(
                    "endHour"
                )
                is not None
            ):
                entities[
                    "ambiguousEndHour"
                ] = int(
                    time_entities["endHour"]
                )
                entities[
                    "ambiguousEndMinute"
                ] = int(
                    time_entities.get(
                        "endMinute"
                    )
                    or 0
                )

            if meridiem:
                if (
                    not entities.get(
                        "startTime"
                    )
                    and entities.get(
                        "ambiguousStartHour"
                    )
                    is not None
                ):
                    entities["startTime"] = (
                        _format_time(
                            _apply_meridiem(
                                int(
                                    entities[
                                        "ambiguousStartHour"
                                    ]
                                ),
                                str(meridiem),
                            ),
                            int(
                                entities.get(
                                    "ambiguousStartMinute"
                                )
                                or 0
                            ),
                        )
                    )
                    entities.pop(
                        "ambiguousStartHour",
                        None,
                    )
                    entities.pop(
                        "ambiguousStartMinute",
                        None,
                    )

                if (
                    not entities.get(
                        "endTime"
                    )
                    and entities.get(
                        "ambiguousEndHour"
                    )
                    is not None
                ):
                    entities["endTime"] = (
                        _format_time(
                            _apply_meridiem(
                                int(
                                    entities[
                                        "ambiguousEndHour"
                                    ]
                                ),
                                str(meridiem),
                            ),
                            int(
                                entities.get(
                                    "ambiguousEndMinute"
                                )
                                or 0
                            ),
                        )
                    )
                    entities.pop(
                        "ambiguousEndHour",
                        None,
                    )
                    entities.pop(
                        "ambiguousEndMinute",
                        None,
                    )

        else:
            time_value = time_entities.get(
                "time"
            )

            if time_value:
                entities["time"] = time_value
                entities.pop(
                    "ambiguousHour",
                    None,
                )
                entities.pop(
                    "ambiguousMinute",
                    None,
                )

            elif (
                time_entities.get("ambiguous")
                and time_entities.get("hour")
                is not None
            ):
                entities["ambiguousHour"] = (
                    int(time_entities["hour"])
                )
                entities["ambiguousMinute"] = (
                    int(
                        time_entities.get(
                            "minute"
                        )
                        or 0
                    )
                )

            elif (
                meridiem
                and entities.get(
                    "ambiguousHour"
                )
                is not None
            ):
                entities["time"] = _format_time(
                    _apply_meridiem(
                        int(
                            entities[
                                "ambiguousHour"
                            ]
                        ),
                        str(meridiem),
                    ),
                    int(
                        entities.get(
                            "ambiguousMinute"
                        )
                        or 0
                    ),
                )
                entities.pop(
                    "ambiguousHour",
                    None,
                )
                entities.pop(
                    "ambiguousMinute",
                    None,
                )

    return entities


def _required_fields(
    domain: str,
    intent: str,
    entities: dict[str, Any],
    time_entities: dict[str, Any],
) -> list[str]:
    missing: list[str] = []

    if intent == "RESERVE_FOOD":
        if not (
            entities.get("date")
            or entities.get("dateScope")
        ):
            missing.append("date")

    elif intent in {
        "CREATE_LEAVE",
        "CREATE_MISSION",
    }:
        if not entities.get("startDate"):
            missing.append("date")

    elif intent == "CREATE_TIME_EVENT":
        if not entities.get("date"):
            missing.append("date")

        if (
            time_entities.get("ambiguous")
            or entities.get(
                "ambiguousHour"
            )
            is not None
        ):
            missing.append("meridiem")

        elif not entities.get("time"):
            missing.append("time")

        if not entities.get("eventType"):
            missing.append("eventType")

    elif intent == "CREATE_TIME_EVENT_RANGE":
        if not entities.get("date"):
            missing.append("date")

        if (
            time_entities.get(
                "startAmbiguous"
            )
            or time_entities.get(
                "endAmbiguous"
            )
            or entities.get(
                "ambiguousStartHour"
            )
            is not None
            or entities.get(
                "ambiguousEndHour"
            )
            is not None
        ):
            missing.append("meridiem")

        if not entities.get("startTime"):
            missing.append("startTime")

        if not entities.get("endTime"):
            missing.append("endTime")

    elif intent in {
        "FOOD_UNKNOWN",
        "LEAVE_UNKNOWN",
        "MISSION_UNKNOWN",
        "NEEDS_DOMAIN",
    }:
        missing.append("intent")

    return list(dict.fromkeys(missing))


def _clarification_message(
    *,
    domain: str,
    intent: str,
    missing_fields: list[str],
    errors: list[str],
) -> str | None:
    if errors:
        return (
            f"{errors[0]} "
            "برای نمونه بنویسید: "
            "ساعت ۱۰ و ۵۰ دقیقه."
        )

    if "meridiem" in missing_fields:
        return (
            "منظورتان صبح است یا شب؟ "
            "برای نمونه: ساعت ۱۰ صبح "
            "یا ساعت ۱۰ شب."
        )

    if "date" in missing_fields:
        if domain == "FOOD":
            return (
                "برای چه روزی غذا رزرو شود؟ "
                "مثلاً امروز، فردا یا کل هفته."
            )

        return (
            "تاریخ درخواست را بفرمایید؛ "
            "مثلاً امروز، فردا یا "
            "۱۴۰۵/۰۴/۲۵."
        )

    if "time" in missing_fields:
        return (
            "ساعت تردد را بفرمایید؛ "
            "مثلاً ساعت ۸ صبح یا "
            "۱۰ و ۵۰ دقیقه شب."
        )

    if "eventType" in missing_fields:
        return (
            "این تردد مربوط به ورود است "
            "یا خروج؟"
        )

    if "startTime" in missing_fields:
        return (
            "ساعت شروع تردد را بفرمایید."
        )

    if "endTime" in missing_fields:
        return (
            "ساعت پایان تردد را بفرمایید."
        )

    if "intent" in missing_fields:
        if domain == "FOOD":
            return (
                "موضوع غذا را متوجه شدم. "
                "می‌خواهید منو را ببینید، "
                "غذا رزرو کنید یا رزرو را "
                "لغو کنید؟"
            )

        if domain == "LEAVE":
            return (
                "موضوع مرخصی را متوجه شدم. "
                "می‌خواهید مانده مرخصی را "
                "ببینید یا درخواست جدید "
                "ثبت کنید؟"
            )

        return (
            "لطفاً مشخص کنید چه کاری باید "
            "انجام شود؛ مثلاً رزرو غذا، "
            "ثبت مرخصی یا ثبت تردد."
        )

    if intent == "EMPTY_MESSAGE":
        return (
            "پیام شما خالی است. "
            "برای نمونه بنویسید: "
            "مانده مرخصی من چقدره؟"
        )

    return None


def _rejection_message(
    domain: str,
    parent_intent: str | None,
) -> str:
    if domain == "FOOD":
        return (
            "باشه، پیشنهاد قبلی را انجام نمی‌دهم. "
            "روز یا غذای دیگری را بگویید."
        )

    if domain == "LEAVE":
        return (
            "باشه، درخواست قبلی ثبت نمی‌شود. "
            "تاریخ یا نوع درخواست دیگری را بگویید."
        )

    if domain == "MISSION":
        return (
            "باشه، مأموریت قبلی ثبت نمی‌شود. "
            "جزئیات جدید را بگویید."
        )

    if domain == "ATTENDANCE":
        return (
            "باشه، تردد قبلی ثبت نمی‌شود. "
            "تاریخ، ساعت یا نوع تردد جدید را بگویید."
        )

    if parent_intent:
        return (
            "باشه، پیشنهاد قبلی انجام نمی‌شود. "
            "درخواست جدیدتان را بگویید."
        )

    return (
        "باشه، آن مورد انجام نمی‌شود. "
        "درخواست جدیدتان را بگویید."
    )


def _confidence_for(
    domain: str,
    intent: str,
) -> float:
    if intent in {
        "UNSUPPORTED",
        "EMPTY_MESSAGE",
    }:
        return 0.99

    if intent in {
        "FOOD_UNKNOWN",
        "LEAVE_UNKNOWN",
        "MISSION_UNKNOWN",
        "NEEDS_DOMAIN",
    }:
        return 0.65

    if domain != "UNKNOWN":
        return 0.95

    return 0.50


def _is_read_only_intent(
    intent: str,
) -> bool:
    return intent in {
        "GET_LEAVE_BALANCE",
        "SHOW_LEAVE_REQUESTS",
        "SHOW_MISSIONS",
        "SHOW_ATTENDANCE",
        "SHOW_FOOD_MENU",
        "SHOW_FOOD_RESERVATION",
        "UNSUPPORTED",
    }


def _build_state(
    *,
    domain: str,
    intent: str,
    entities: dict[str, Any],
    missing_fields: list[str],
) -> dict[str, Any]:
    if intent in {
        "UNSUPPORTED",
        "EMPTY_MESSAGE",
        "CANCEL_CONVERSATION",
    }:
        return {}

    return {
        "domain": domain,
        "intent": intent,
        "entities": dict(entities),
        "missingFields": list(
            missing_fields
        ),
    }


# ============================================================
# Public API
# ============================================================

def analyze_message(
    message: str,
    *,
    reference_date: str,
    conversation_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = normalize_text(message)
    previous_state = (
        dict(conversation_state)
        if isinstance(
            conversation_state,
            dict,
        )
        else {}
    )

    if not text:
        return {
            "domain": "UNKNOWN",
            "intent": "EMPTY_MESSAGE",
            "entities": {},
            "confidence": 1.0,
            "missingFields": [
                "message"
            ],
            "needsClarification": True,
            "conversationComplete": False,
            "clarification": (
                "پیام شما خالی است. "
                "لطفاً درخواستتان را بنویسید."
            ),
            "errors": [],
            "state": {},
        }

    # --------------------------------------------------------
    # Explicit conversation cancellation
    # --------------------------------------------------------

    if previous_state:
        normalized_cancel_values = {
            normalize_text(value)
            for value in (
                _CANCEL_CONVERSATION_PHRASES
            )
        }

        has_domain_word = (
            _contains_any_word(
                text,
                _FOOD_WORDS,
            )
            or _contains_word(
                text,
                "مرخصی",
            )
            or _contains_word(
                text,
                "ماموریت",
            )
            or _contains_any_word(
                text,
                {
                    "تردد",
                    "ورود",
                    "خروج",
                },
            )
        )

        if (
            text in normalized_cancel_values
            or (
                _contains_word(
                    text,
                    "بیخیال",
                )
                and not has_domain_word
            )
        ):
            return {
                "domain": (
                    previous_state.get(
                        "domain"
                    )
                    or "UNKNOWN"
                ),
                "intent": (
                    "CANCEL_CONVERSATION"
                ),
                "entities": {},
                "confidence": 1.0,
                "missingFields": [],
                "needsClarification": False,
                "conversationComplete": True,
                "clarification": None,
                "errors": [],
                "state": {},
            }

    # --------------------------------------------------------
    # Explicit rejection without ending the conversation
    # --------------------------------------------------------

    if previous_state:
        normalized_reject_values = {
            normalize_text(value)
            for value in _REJECT_PHRASES
        }

        if text in normalized_reject_values:
            previous_domain_value = str(
                previous_state.get(
                    "domain"
                )
                or "UNKNOWN"
            )

            previous_intent_value = (
                previous_state.get(
                    "intent"
                )
            )

            previous_entities_value = (
                previous_state.get(
                    "entities"
                )
                if isinstance(
                    previous_state.get(
                        "entities"
                    ),
                    dict,
                )
                else {}
            )

            rejected_state = {
                "domain": (
                    previous_domain_value
                ),
                "intent": (
                    str(
                        previous_intent_value
                        or "NEEDS_DOMAIN"
                    )
                ),
                "entities": dict(
                    previous_entities_value
                ),
                "missingFields": [
                    "alternative"
                ],
                "proposalRejected": True,
            }

            return {
                "domain": (
                    previous_domain_value
                ),
                "intent": "REJECT",
                "entities": {
                    **dict(
                        previous_entities_value
                    ),
                    "parentIntent": (
                        previous_intent_value
                    ),
                },
                "confidence": 1.0,
                "missingFields": [
                    "alternative"
                ],
                "needsClarification": True,
                "conversationComplete": False,
                "clarification": (
                    _rejection_message(
                        previous_domain_value,
                        (
                            str(
                                previous_intent_value
                            )
                            if previous_intent_value
                            else None
                        ),
                    )
                ),
                "errors": [],
                "state": rejected_state,
            }

    # --------------------------------------------------------
    # Explicit confirmation
    # --------------------------------------------------------

    normalized_confirm_values = {
        normalize_text(value)
        for value in _CONFIRM_PHRASES
    }

    if (
        previous_state
        and text in normalized_confirm_values
    ):
        if previous_state.get(
            "proposalRejected"
        ):
            previous_domain_value = str(
                previous_state.get(
                    "domain"
                )
                or "UNKNOWN"
            )

            return {
                "domain": (
                    previous_domain_value
                ),
                "intent": "REJECT",
                "entities": dict(
                    previous_state.get(
                        "entities"
                    )
                    or {}
                ),
                "confidence": 1.0,
                "missingFields": [
                    "alternative"
                ],
                "needsClarification": True,
                "conversationComplete": False,
                "clarification": (
                    "پیشنهاد قبلی رد شده است. "
                    "لطفاً گزینه یا جزئیات جدید "
                    "را بگویید."
                ),
                "errors": [],
                "state": previous_state,
            }

        parent_intent = (
            previous_state.get("intent")
        )

        parent_entities = (
            previous_state.get("entities")
            if isinstance(
                previous_state.get(
                    "entities"
                ),
                dict,
            )
            else {}
        )

        entities = dict(parent_entities)
        entities["parentIntent"] = (
            parent_intent
        )

        return {
            "domain": (
                previous_state.get(
                    "domain"
                )
                or "UNKNOWN"
            ),
            "intent": "CONFIRM",
            "entities": entities,
            "confidence": 1.0,
            "missingFields": [],
            "needsClarification": False,
            "conversationComplete": True,
            "clarification": None,
            "errors": [],
            "state": previous_state,
        }

    time_entities = (
        _extract_time_entities(text)
    )

    detected_domain, detected_intent = (
        _detect_domain_intent(
            text,
            time_entities,
        )
    )

    previous_domain = (
        previous_state.get("domain")
    )

    previous_intent = (
        previous_state.get("intent")
    )

    current_has_known_domain = (
        detected_domain
        not in {
            "UNKNOWN",
            "OUT_OF_SCOPE",
        }
    )

    has_new_entities = bool(
        _extract_date(
            text,
            reference_date,
        )
        or time_entities.get("time")
        or time_entities.get("startTime")
        or time_entities.get("endTime")
        or _extract_event_type(text)
        or _extract_meridiem(text)
        or _contains_phrase(
            text,
            "این هفته",
        )
        or _contains_phrase(
            text,
            "هفته بعد",
        )
    )

    # Continue the previous conversation when the new
    # message only supplies missing information.
    if (
        previous_state
        and not current_has_known_domain
        and has_new_entities
    ):
        domain = (
            str(previous_domain)
            if previous_domain
            else "UNKNOWN"
        )

        intent = (
            str(previous_intent)
            if previous_intent
            else "NEEDS_DOMAIN"
        )

    else:
        domain = detected_domain
        intent = detected_intent

    previous_entities = (
        previous_state.get("entities")
        if (
            previous_state
            and isinstance(
                previous_state.get(
                    "entities"
                ),
                dict,
            )
            and domain
            == previous_state.get(
                "domain"
            )
        )
        else {}
    )

    entities = _build_entities(
        text=text,
        domain=domain,
        intent=intent,
        reference_date=reference_date,
        previous_entities=(
            previous_entities
        ),
        time_entities=time_entities,
    )

    # A corrective message such as:
    # "نه، ساعت ده و پنجاه دقیقه شب"
    # must replace the previous time.
    if (
        previous_state
        and has_new_entities
        and _contains_word(text, "نه")
    ):
        previous_intent_value = (
            previous_state.get("intent")
        )

        if previous_intent_value:
            intent = str(
                previous_intent_value
            )

        previous_domain_value = (
            previous_state.get("domain")
        )

        if previous_domain_value:
            domain = str(
                previous_domain_value
            )

    errors = list(
        time_entities.get("errors")
        or []
    )

    missing_fields = _required_fields(
        domain,
        intent,
        entities,
        time_entities,
    )

    if errors and "time" not in missing_fields:
        missing_fields.append("time")

    needs_clarification = bool(
        missing_fields
        or errors
    )

    clarification = (
        _clarification_message(
            domain=domain,
            intent=intent,
            missing_fields=missing_fields,
            errors=errors,
        )
    )

    if intent == "UNSUPPORTED":
        clarification = (
            "این درخواست خارج از حوزه خدمات "
            "فعلی من است. من می‌توانم در امور "
            "غذا، مرخصی، مأموریت و تردد "
            "کمکتان کنم."
        )

    if intent == "NEEDS_DOMAIN":
        clarification = (
            "چه چیزی ثبت شود؟ "
            "برای نمونه بنویسید: "
            "رزرو غذا برای فردا، "
            "ثبت مرخصی یا ثبت تردد."
        )

    conversation_complete = (
        not needs_clarification
        and _is_read_only_intent(
            intent
        )
    )

    if intent == "UNSUPPORTED":
        conversation_complete = True

    state = _build_state(
        domain=domain,
        intent=intent,
        entities=entities,
        missing_fields=missing_fields,
    )

    return {
        "domain": domain,
        "intent": intent,
        "entities": entities,
        "confidence": _confidence_for(
            domain,
            intent,
        ),
        "missingFields": (
            missing_fields
        ),
        "needsClarification": (
            needs_clarification
        ),
        "conversationComplete": (
            conversation_complete
        ),
        "clarification": clarification,
        "errors": errors,
        "state": state,
    }


__all__ = [
    "analyze_message",
    "normalize_text",
]

# NLU_CONTEXT_TIME_FINAL_V1
#
# This layer preserves the existing NLU implementation and adds:
# - strict domain isolation
# - common typo normalization
# - contextual short time parsing
# - morning/night clarification
# - safe handling of ambiguous attendance requests

_ORIGINAL_NORMALIZE_TEXT_CONTEXT_V1 = normalize_text
_ORIGINAL_ANALYZE_MESSAGE_CONTEXT_V1 = analyze_message


_CONTEXT_TYPO_REPLACEMENTS_V1 = {
    "اسحقاقی": "استحقاقی",
    "اسحقاقى": "استحقاقی",
    "ترد": "تردد",
    "یکشنیه": "یکشنبه",
    "یکشبه": "یکشنبه",
    "سهشنه": "سه شنبه",
    "سهشنیه": "سه شنبه",
    "چهارشنه": "چهارشنبه",
    "پنجشنه": "پنجشنبه",
}


_CONTEXT_MERIDIEM_V1 = {
    "صبح": "AM",
    "بامداد": "AM",
    "ظهر": "PM",
    "بعدازظهر": "PM",
    "بعد از ظهر": "PM",
    "عصر": "PM",
    "شب": "PM",
}


_CONTEXT_SMALL_NUMBERS_V1 = {
    "صفر": 0,
    "یک": 1,
    "دو": 2,
    "سه": 3,
    "چهار": 4,
    "پنج": 5,
    "شش": 6,
    "هفت": 7,
    "هشت": 8,
    "نه": 9,
    "ده": 10,
    "یازده": 11,
    "دوازده": 12,
    "سیزده": 13,
    "چهارده": 14,
    "پانزده": 15,
    "شانزده": 16,
    "هفده": 17,
    "هجده": 18,
    "نوزده": 19,
}


_CONTEXT_TENS_V1 = {
    "بیست": 20,
    "سی": 30,
    "چهل": 40,
    "پنجاه": 50,
}


def _context_replace_exact_word_v1(
    text: str,
    old: str,
    new: str,
) -> str:
    return re.sub(
        (
            r"(?<![A-Za-z0-9_\u0600-\u06FF])"
            + re.escape(old)
            + r"(?![A-Za-z0-9_\u0600-\u06FF])"
        ),
        new,
        text,
    )


def normalize_text(
    value: Any,
) -> str:
    text = (
        _ORIGINAL_NORMALIZE_TEXT_CONTEXT_V1(
            value
        )
    )

    for old, new in (
        _CONTEXT_TYPO_REPLACEMENTS_V1.items()
    ):
        text = _context_replace_exact_word_v1(
            text,
            old,
            new,
        )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def _context_tokens_v1(
    text: str,
) -> set[str]:
    return set(
        re.findall(
            (
                r"[A-Za-z]+|"
                r"[0-9]+|"
                r"[\u0600-\u06FF]+"
            ),
            normalize_text(text),
        )
    )


def _context_explicit_domain_v1(
    text: str,
) -> str | None:
    tokens = _context_tokens_v1(
        text
    )

    if "ماموریت" in tokens:
        return "MISSION"

    if "مرخصی" in tokens:
        return "LEAVE"

    if tokens.intersection(
        {
            "تردد",
            "ورود",
            "خروج",
            "ساعتزنی",
        }
    ):
        return "ATTENDANCE"

    if tokens.intersection(
        {
            "غذا",
            "غذای",
            "منو",
            "ناهار",
            "رستوران",
        }
    ):
        return "FOOD"

    return None


def _context_parse_number_words_v1(
    value: str,
) -> int | None:
    normalized = normalize_text(
        value
    )

    if normalized.isdigit():
        return int(normalized)

    if normalized in (
        _CONTEXT_SMALL_NUMBERS_V1
    ):
        return (
            _CONTEXT_SMALL_NUMBERS_V1[
                normalized
            ]
        )

    if normalized in _CONTEXT_TENS_V1:
        return _CONTEXT_TENS_V1[
            normalized
        ]

    parts = [
        part.strip()
        for part in normalized.split(
            " و "
        )
        if part.strip()
    ]

    if len(parts) != 2:
        return None

    tens = _CONTEXT_TENS_V1.get(
        parts[0]
    )

    unit = (
        _CONTEXT_SMALL_NUMBERS_V1.get(
            parts[1]
        )
    )

    if (
        tens is None
        or unit is None
        or not 0 <= unit <= 9
    ):
        return None

    return tens + unit


def _context_parse_short_time_v1(
    text: str,
) -> tuple[
    int,
    int,
    str | None,
] | None:
    normalized = normalize_text(
        text
    )

    meridiem = None

    for phrase, value in sorted(
        _CONTEXT_MERIDIEM_V1.items(),
        key=lambda item: len(
            item[0]
        ),
        reverse=True,
    ):
        if normalized == phrase:
            return None

        suffix = " " + phrase

        if normalized.endswith(
            suffix
        ):
            meridiem = value

            normalized = normalized[
                :-len(suffix)
            ].strip()

            break

    normalized = re.sub(
        r"^ساعت\s+",
        "",
        normalized,
    ).strip()

    match = re.fullmatch(
        (
            r"(?P<hour>[0-9]{1,2})"
            r"(?:\s+و\s+"
            r"(?P<minute>.+?))?"
        ),
        normalized,
    )

    if not match:
        return None

    hour = int(
        match.group("hour")
    )

    if not 0 <= hour <= 23:
        return None

    minute_text = str(
        match.group("minute")
        or ""
    ).strip()

    if not minute_text:
        minute = 0

    else:
        minute_text = re.sub(
            r"\s+دقیقه$",
            "",
            minute_text,
        ).strip()

        if minute_text == "نیم":
            minute = 30

        elif minute_text == "ربع":
            minute = 15

        elif minute_text == "سه ربع":
            minute = 45

        else:
            parsed_minute = (
                _context_parse_number_words_v1(
                    minute_text
                )
            )

            if parsed_minute is None:
                return None

            minute = parsed_minute

    if not 0 <= minute <= 59:
        return None

    return (
        hour,
        minute,
        meridiem,
    )


def _context_apply_meridiem_v1(
    hour: int,
    meridiem: str,
) -> int:
    if meridiem == "AM":
        if hour == 12:
            return 0

        return hour

    if meridiem == "PM":
        if hour >= 12:
            return hour

        return hour + 12

    return hour


def _context_attendance_result_v1(
    previous_state: dict[str, Any],
    *,
    hour: int,
    minute: int,
    meridiem: str | None,
) -> dict[str, Any] | None:
    previous_domain = str(
        previous_state.get(
            "domain"
        )
        or ""
    )

    previous_intent = str(
        previous_state.get(
            "intent"
        )
        or ""
    )

    if (
        previous_domain
        != "ATTENDANCE"
        or previous_intent
        != "CREATE_TIME_EVENT"
    ):
        return None

    previous_entities = (
        previous_state.get(
            "entities"
        )
        if isinstance(
            previous_state.get(
                "entities"
            ),
            dict,
        )
        else {}
    )

    entities = dict(
        previous_entities
    )

    previous_missing = (
        previous_state.get(
            "missingFields"
        )
        if isinstance(
            previous_state.get(
                "missingFields"
            ),
            list,
        )
        else []
    )

    missing_fields = [
        str(item)
        for item in previous_missing
        if str(item)
        not in {
            "time",
            "meridiem",
        }
    ]

    if (
        meridiem is None
        and 1 <= hour <= 12
    ):
        entities.pop(
            "time",
            None,
        )

        entities[
            "ambiguousHour"
        ] = hour

        entities[
            "ambiguousMinute"
        ] = minute

        missing_fields = [
            "meridiem",
            *[
                item
                for item in missing_fields
                if item != "meridiem"
            ],
        ]

        if minute == 0:
            time_label = str(hour)

        elif minute == 30:
            time_label = (
                f"{hour} و نیم"
            )

        else:
            time_label = (
                f"{hour} و {minute} دقیقه"
            )

        clarification = (
            f"منظورتان ساعت "
            f"{time_label} صبح است "
            f"یا ساعت {time_label} شب؟"
        )

    else:
        resolved_hour = hour

        if meridiem is not None:
            resolved_hour = (
                _context_apply_meridiem_v1(
                    hour,
                    meridiem,
                )
            )

        entities["time"] = (
            f"{resolved_hour:02d}:"
            f"{minute:02d}"
        )

        entities.pop(
            "ambiguousHour",
            None,
        )

        entities.pop(
            "ambiguousMinute",
            None,
        )

        if "eventType" in missing_fields:
            clarification = (
                "این تردد مربوط به "
                "ورود است یا خروج؟"
            )

        else:
            clarification = None

    state = {
        "domain": "ATTENDANCE",
        "intent": (
            "CREATE_TIME_EVENT"
        ),
        "entities": entities,
        "missingFields": (
            missing_fields
        ),
    }

    return {
        "domain": "ATTENDANCE",
        "intent": (
            "CREATE_TIME_EVENT"
        ),
        "entities": entities,
        "confidence": 1.0,
        "missingFields": (
            missing_fields
        ),
        "needsClarification": bool(
            missing_fields
        ),
        "conversationComplete": (
            not missing_fields
        ),
        "clarification": (
            clarification
        ),
        "errors": [],
        "state": state,
    }


def _context_meridiem_reply_v1(
    text: str,
    previous_state: dict[str, Any],
) -> dict[str, Any] | None:
    normalized = normalize_text(
        text
    )

    meridiem = (
        _CONTEXT_MERIDIEM_V1.get(
            normalized
        )
    )

    if meridiem is None:
        return None

    previous_entities = (
        previous_state.get(
            "entities"
        )
        if isinstance(
            previous_state.get(
                "entities"
            ),
            dict,
        )
        else {}
    )

    raw_hour = (
        previous_entities.get(
            "ambiguousHour"
        )
    )

    if raw_hour is None:
        return None

    try:
        hour = int(raw_hour)

        minute = int(
            previous_entities.get(
                "ambiguousMinute"
            )
            or 0
        )

    except (
        TypeError,
        ValueError,
    ):
        return None

    return (
        _context_attendance_result_v1(
            previous_state,
            hour=hour,
            minute=minute,
            meridiem=meridiem,
        )
    )


def _context_postprocess_leave_v1(
    normalized: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    if (
        result.get("domain")
        != "LEAVE"
        or result.get("intent")
        != "LEAVE_UNKNOWN"
    ):
        return result

    tokens = _context_tokens_v1(
        normalized
    )

    has_leave_type = bool(
        tokens.intersection(
            {
                "استحقاقی",
                "استعلاجی",
                "ساعتی",
                "روزانه",
            }
        )
    )

    entities_value = result.get(
        "entities"
    )

    entities = (
        dict(entities_value)
        if isinstance(
            entities_value,
            dict,
        )
        else {}
    )

    has_date = bool(
        entities.get("startDate")
        or entities.get("date")
    )

    if not (
        "مرخصی" in tokens
        and has_leave_type
        and has_date
    ):
        return result

    updated = dict(result)

    updated["intent"] = (
        "CREATE_LEAVE"
    )

    updated[
        "missingFields"
    ] = []

    updated[
        "needsClarification"
    ] = False

    updated[
        "conversationComplete"
    ] = False

    updated[
        "clarification"
    ] = None

    updated[
        "confidence"
    ] = max(
        float(
            updated.get(
                "confidence"
            )
            or 0
        ),
        0.95,
    )

    updated["state"] = {
        "domain": "LEAVE",
        "intent": (
            "CREATE_LEAVE"
        ),
        "entities": entities,
        "missingFields": [],
    }

    return updated


def _context_postprocess_attendance_v1(
    normalized: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    if (
        result.get("domain")
        != "ATTENDANCE"
        or result.get("intent")
        != "SHOW_ATTENDANCE"
    ):
        return result

    read_terms = (
        "نشان بده",
        "نمایش",
        "سوابق",
        "گزارش",
        "لیست",
        "ببین",
        "بررسی کن",
        "چه ترددی",
        "چند تردد",
    )

    create_terms = (
        "ثبت",
        "بزن",
        "ایجاد",
        "درج",
        "ساعت بزن",
    )

    if any(
        term in normalized
        for term in read_terms
    ):
        return result

    if any(
        term in normalized
        for term in create_terms
    ):
        return result

    entities_value = result.get(
        "entities"
    )

    entities = (
        dict(entities_value)
        if isinstance(
            entities_value,
            dict,
        )
        else {}
    )

    if not (
        entities.get("date")
        and any(
            term in normalized
            for term in (
                "تردد",
                "ورود",
                "خروج",
            )
        )
    ):
        return result

    updated = dict(result)

    updated["intent"] = (
        "ATTENDANCE_UNKNOWN"
    )

    updated[
        "missingFields"
    ] = ["intent"]

    updated[
        "needsClarification"
    ] = True

    updated[
        "conversationComplete"
    ] = False

    updated[
        "clarification"
    ] = (
        "می‌خواهید تردد این تاریخ "
        "را ثبت کنید یا سوابق تردد "
        "را ببینید؟"
    )

    updated[
        "confidence"
    ] = max(
        float(
            updated.get(
                "confidence"
            )
            or 0
        ),
        0.9,
    )

    updated["state"] = {
        "domain": "ATTENDANCE",
        "intent": (
            "ATTENDANCE_UNKNOWN"
        ),
        "entities": entities,
        "missingFields": [
            "intent"
        ],
    }

    return updated


def analyze_message(
    message: str,
    *,
    reference_date: str,
    conversation_state: (
        dict[str, Any]
        | None
    ) = None,
) -> dict[str, Any]:
    normalized = normalize_text(
        message
    )

    previous_state = (
        dict(conversation_state)
        if isinstance(
            conversation_state,
            dict,
        )
        else {}
    )

    explicit_domain = (
        _context_explicit_domain_v1(
            normalized
        )
    )

    previous_domain = str(
        previous_state.get(
            "domain"
        )
        or ""
    )

    # A clearly named new domain always wins.
    if (
        explicit_domain
        and previous_domain
        and explicit_domain
        != previous_domain
    ):
        previous_state = {}

    if previous_state:
        meridiem_result = (
            _context_meridiem_reply_v1(
                normalized,
                previous_state,
            )
        )

        if meridiem_result is not None:
            return meridiem_result

        parsed_short_time = (
            _context_parse_short_time_v1(
                normalized
            )
        )

        if parsed_short_time is not None:
            (
                hour,
                minute,
                meridiem,
            ) = parsed_short_time

            attendance_result = (
                _context_attendance_result_v1(
                    previous_state,
                    hour=hour,
                    minute=minute,
                    meridiem=meridiem,
                )
            )

            if attendance_result is not None:
                return attendance_result

    result = (
        _ORIGINAL_ANALYZE_MESSAGE_CONTEXT_V1(
            normalized,
            reference_date=(
                reference_date
            ),
            conversation_state=(
                previous_state
                if previous_state
                else None
            ),
        )
    )

    if not isinstance(
        result,
        dict,
    ):
        return result

    # Defensive retry without old state if an explicit
    # new domain was routed somewhere else.
    if (
        explicit_domain
        and result.get("domain")
        != explicit_domain
    ):
        clean_result = (
            _ORIGINAL_ANALYZE_MESSAGE_CONTEXT_V1(
                normalized,
                reference_date=(
                    reference_date
                ),
                conversation_state=None,
            )
        )

        if isinstance(
            clean_result,
            dict,
        ):
            result = clean_result

    result = (
        _context_postprocess_leave_v1(
            normalized,
            result,
        )
    )

    result = (
        _context_postprocess_attendance_v1(
            normalized,
            result,
        )
    )

    return result

