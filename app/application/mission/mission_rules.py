from __future__ import annotations


MISSION_CREATE_KEYWORDS = [
    "ثبت ماموریت",
    "درخواست ماموریت",
    "ماموریت ثبت کن",
]


MISSION_DELETE_KEYWORDS = [
    "لغو ماموریت",
    "حذف ماموریت",
    "کنسل ماموریت",
]


MISSION_LIST_KEYWORDS = [
    "لیست ماموریت",
    "درخواست های ماموریت",
    "درخواست‌های ماموریت",
    "ماموریت های من",
    "ماموریت‌های من",
]


def is_mission_create(
    text: str,
) -> bool:

    return any(
        keyword in text
        for keyword in MISSION_CREATE_KEYWORDS
    )


def is_mission_delete(
    text: str,
) -> bool:

    return any(
        keyword in text
        for keyword in MISSION_DELETE_KEYWORDS
    )


def is_mission_list(
    text: str,
) -> bool:

    return any(
        keyword in text
        for keyword in MISSION_LIST_KEYWORDS
    )