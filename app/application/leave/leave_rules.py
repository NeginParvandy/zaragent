from __future__ import annotations


LEAVE_CREATE_KEYWORDS = [
    "مرخصی بگیر",
    "ثبت مرخصی",
    "درخواست مرخصی",
    "مرخصی ثبت کن",
]


LEAVE_LIST_KEYWORDS = [
    "درخواست های مرخصی",
    "درخواست‌های مرخصی",
    "لیست مرخصی",
    "مرخصی های من",
    "مرخصی‌های من",
    "نمایش مرخصی",
    "نمایش درخواست",
    "نشان بده مرخصی",
    "درخواست های من",
    "درخواست‌های من",
    "وضعیت مرخصی",
]


LEAVE_DELETE_KEYWORDS = [
    "لغو مرخصی",
    "حذف مرخصی",
    "کنسل مرخصی",
]


LEAVE_BALANCE_KEYWORDS = [
    "مانده مرخصی",
    "چقدر مرخصی دارم",
    "باقی مانده مرخصی",
]


def is_leave_create(text: str) -> bool:
    return any(
        keyword in text
        for keyword in LEAVE_CREATE_KEYWORDS
    )


def is_leave_list(text: str) -> bool:
    return any(
        keyword in text
        for keyword in LEAVE_LIST_KEYWORDS
    )


def is_delete_leave(text: str) -> bool:
    return any(
        keyword in text
        for keyword in LEAVE_DELETE_KEYWORDS
    )


def is_leave_balance(text: str) -> bool:
    return any(
        keyword in text
        for keyword in LEAVE_BALANCE_KEYWORDS
    )