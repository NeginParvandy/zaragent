from __future__ import annotations


REPORT_KEYWORDS = [
    "گزارش",
    "گزارش ماهانه",
    "خلاصه عملکرد",
    "گزارش عملکرد",
]


def is_report_request(
    text: str,
) -> bool:

    return any(
        keyword in text
        for keyword in REPORT_KEYWORDS
    )