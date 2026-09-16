from __future__ import annotations


ATTENDANCE_KEYWORDS = [
    "تردد",
    "ورود",
    "خروج",
    "ساعت زنی",
    "ساعت‌زنی",
]


def is_attendance_text(text: str) -> bool:
    return any(
        keyword in text
        for keyword in ATTENDANCE_KEYWORDS
    )