from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(r"D:\serviceAi")

# شنبه تا چهارشنبه
WORKDAYS = {
    5,
    6,
    0,
    1,
    2,
}

WEEKDAY_FA = {
    0: "دوشنبه",
    1: "سه‌شنبه",
    2: "چهارشنبه",
    3: "پنجشنبه",
    4: "جمعه",
    5: "شنبه",
    6: "یکشنبه",
}

# ورود تا 08:15 مجاز است.
ENTRY_LIMIT = 8 * 60 + 15

# ساعت خروج استاندارد.
EXIT_STANDARD = 17 * 60

# یک رویداد تا ساعت 12 به‌عنوان ورود
# و بعد از آن به‌عنوان خروج در نظر گرفته می‌شود.
SINGLE_EVENT_ENTRY_LIMIT = 12 * 60

PENDING_LEAVE = {
    "SENT",
    "PENDING",
    "SUBMITTED",
    "INPROCESS",
    "IN_PROCESS",
    "WAITING",
}

REJECTED_LEAVE = {
    "REJECTED",
    "CANCELLED",
    "CANCELED",
    "DELETED",
    "WITHDRAWN",
}

APPROVED_LEAVE = {
    "APPROVED",
    "POSTED",
    "ACCEPTED",
    "COMPLETED",
    "DONE",
}

LABELS = {
    "POSSIBLE_ABSENCE": "غیبت احتمالی",
    "MISSING_ENTRY": "ورود ثبت نشده",
    "MISSING_EXIT": "خروج ثبت نشده",
    "LATE_ENTRY": "تأخیر ورود",
    "EARLY_EXIT": "خروج زودهنگام",
    "EXTRA_EVENTS": "ترددهای اضافی یا تکراری",
    "LEAVE_ATTENDANCE_CONFLICT": (
        "تداخل مرخصی و تردد"
    ),
    "LEAVE_PENDING": (
        "مرخصی در انتظار تعیین وضعیت"
    ),
    "LEAVE_STATUS_UNKNOWN": (
        "وضعیت مرخصی نیازمند بررسی"
    ),
}

ACTIONS = {
    "POSSIBLE_ABSENCE": [
        "در محل کار بودم",
        "مرخصی داشتم",
        "مأموریت بودم",
        "غیبت درست است",
    ],
    "MISSING_ENTRY": [
        "ثبت ورود",
        "مرخصی ساعتی داشتم",
        "مأموریت بودم",
        "اطلاعات درست است",
    ],
    "MISSING_EXIT": [
        "ثبت خروج",
        "مرخصی ساعتی داشتم",
        "مأموریت بودم",
        "اطلاعات درست است",
    ],
    "LATE_ENTRY": [
        "ثبت مرخصی ساعتی از 08:00 تا 11:00",
        "مأموریت بودم",
        "تأخیر درست است",
    ],
    "EARLY_EXIT": [
        "ثبت خروج اشتباه است",
        "مرخصی ساعتی داشتم",
        "مأموریت بودم",
        "خروج زودهنگام درست است",
    ],
    "LEAVE_ATTENDANCE_CONFLICT": [
        "مرخصی درست است",
        "در محل کار بودم",
        "وضعیت درخواست را بررسی کن",
    ],
    "LEAVE_PENDING": [
        "وضعیت درخواست را بررسی کن",
        "در محل کار بودم",
    ],
    "LEAVE_STATUS_UNKNOWN": [
        "وضعیت درخواست را بررسی کن",
        "در محل کار بودم",
    ],
}


def parse_jalali(
    text: str,
) -> tuple[int, int, int]:
    match = re.fullmatch(
        r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})",
        text.strip(),
    )

    if not match:
        raise ValueError(
            f"تاریخ شمسی نامعتبر است: {text}"
        )

    jy, jm, jd = map(
        int,
        match.groups(),
    )

    if (
        not 1 <= jm <= 12
        or not 1 <= jd <= 31
    ):
        raise ValueError(
            f"تاریخ شمسی نامعتبر است: {text}"
        )

    return jy, jm, jd


def jalali_to_gregorian(
    jy: int,
    jm: int,
    jd: int,
) -> date:
    jy += 1595

    days = (
        -355668
        + 365 * jy
        + (jy // 33) * 8
        + ((jy % 33) + 3) // 4
        + jd
    )

    if jm < 7:
        days += (jm - 1) * 31
    else:
        days += (
            (jm - 7) * 30
            + 186
        )

    gy = 400 * (
        days // 146097
    )

    days %= 146097

    if days > 36524:
        gy += 100 * (
            (days - 1) // 36524
        )

        days = (
            days - 1
        ) % 36524

        if days >= 365:
            days += 1

    gy += 4 * (
        days // 1461
    )

    days %= 1461

    if days > 365:
        gy += (
            days - 1
        ) // 365

        days = (
            days - 1
        ) % 365

    gd = days + 1

    leap = (
        (
            gy % 4 == 0
            and gy % 100 != 0
        )
        or gy % 400 == 0
    )

    month_days = [
        0,
        31,
        29 if leap else 28,
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ]

    gm = 1

    while (
        gm <= 12
        and gd > month_days[gm]
    ):
        gd -= month_days[gm]
        gm += 1

    return date(
        gy,
        gm,
        gd,
    )


def gregorian_to_jalali(
    value: date,
) -> tuple[int, int, int]:
    gy = value.year
    gm = value.month
    gd = value.day

    cumulative = [
        0,
        31,
        59,
        90,
        120,
        151,
        181,
        212,
        243,
        273,
        304,
        334,
    ]

    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621

    gy2 = (
        gy + 1
        if gm > 2
        else gy
    )

    days = (
        365 * gy
        + (gy2 + 3) // 4
        - (gy2 + 99) // 100
        + (gy2 + 399) // 400
        - 80
        + gd
        + cumulative[gm - 1]
    )

    jy += 33 * (
        days // 12053
    )

    days %= 12053

    jy += 4 * (
        days // 1461
    )

    days %= 1461

    if days > 365:
        jy += (
            days - 1
        ) // 365

        days = (
            days - 1
        ) % 365

    if days < 186:
        jm = 1 + (
            days // 31
        )

        jd = 1 + (
            days % 31
        )

    else:
        jm = 7 + (
            (days - 186) // 30
        )

        jd = 1 + (
            (days - 186) % 30
        )

    return jy, jm, jd


def jalali_text(
    value: date,
) -> str:
    jy, jm, jd = (
        gregorian_to_jalali(
            value
        )
    )

    return (
        f"{jy:04d}/"
        f"{jm:02d}/"
        f"{jd:02d}"
    )


def sap_date(
    value: Any,
) -> date | None:
    text = str(
        value or ""
    ).strip()

    match = re.fullmatch(
        r"/Date\((-?\d+)(?:[+-]\d+)?\)/",
        text,
    )

    if match:
        milliseconds = int(
            match.group(1)
        )

        return datetime.fromtimestamp(
            milliseconds / 1000,
            tz=timezone.utc,
        ).date()

    for fmt in (
        "%Y-%m-%d",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(
                text,
                fmt,
            ).date()

        except ValueError:
            pass

    return None


def time_minutes(
    value: Any,
) -> int | None:
    text = str(
        value or ""
    ).strip().upper()

    match = re.fullmatch(
        r"PT(?:(\d+)H)?"
        r"(?:(\d+)M)?"
        r"(?:(\d+)S)?",
        text,
    )

    if match:
        hour = int(
            match.group(1) or 0
        )

        minute = int(
            match.group(2) or 0
        )

        if (
            0 <= hour <= 23
            and 0 <= minute <= 59
        ):
            return (
                hour * 60
                + minute
            )

        return None

    match = re.fullmatch(
        r"(\d{2})(\d{2})(\d{2})",
        text,
    )

    if match:
        hour = int(
            match.group(1)
        )

        minute = int(
            match.group(2)
        )

        if (
            0 <= hour <= 23
            and 0 <= minute <= 59
        ):
            return (
                hour * 60
                + minute
            )

        return None

    match = re.fullmatch(
        r"(\d{1,2}):(\d{2})"
        r"(?::\d{2})?",
        text,
    )

    if match:
        hour = int(
            match.group(1)
        )

        minute = int(
            match.group(2)
        )

        if (
            0 <= hour <= 23
            and 0 <= minute <= 59
        ):
            return (
                hour * 60
                + minute
            )

    return None


def clock_text(
    value: int | None,
) -> str | None:
    if value is None:
        return None

    hour, minute = divmod(
        value,
        60,
    )

    return (
        f"{hour:02d}:"
        f"{minute:02d}"
    )


def duration_text(
    minutes: int,
) -> str:
    hour, minute = divmod(
        minutes,
        60,
    )

    if hour and minute:
        return (
            f"{hour} ساعت و "
            f"{minute} دقیقه"
        )

    if hour:
        return f"{hour} ساعت"

    return f"{minute} دقیقه"


def load_rows(
    path: Path,
) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(
            f"فایل پیدا نشد: {path}"
        )

    payload = json.loads(
        path.read_text(
            encoding="utf-8-sig"
        )
    )

    rows = (
        payload.get("data")
        if isinstance(
            payload,
            dict,
        )
        else None
    )

    return [
        row
        for row in (
            rows or []
        )
        if isinstance(
            row,
            dict,
        )
    ]


def leave_status(
    row: dict[str, Any],
) -> str:
    status = str(
        row.get("statusID")
        or row.get("status")
        or ""
    ).strip().upper()

    if status in REJECTED_LEAVE:
        return "rejected"

    if status in PENDING_LEAVE:
        return "pending"

    if status in APPROVED_LEAVE:
        return "approved"

    return "unknown"


def group_events(
    rows: list[dict[str, Any]],
) -> dict[
    date,
    list[dict[str, Any]],
]:
    grouped: dict[
        date,
        list[dict[str, Any]],
    ] = defaultdict(list)

    for row in rows:
        day = sap_date(
            row.get("eventdate")
            or row.get("eventDate")
        )

        minute = time_minutes(
            row.get("eventTime")
        )

        if (
            day is None
            or minute is None
        ):
            continue

        grouped[day].append(
            {
                "minute": minute,
                "time": clock_text(
                    minute
                ),
                "requestId": str(
                    row.get("reqId")
                    or ""
                ),
                "status": str(
                    row.get("status")
                    or ""
                ),
            }
        )

    for events in grouped.values():
        events.sort(
            key=lambda item: int(
                item["minute"]
            )
        )

    return dict(grouped)


def group_leaves(
    rows: list[dict[str, Any]],
) -> dict[
    date,
    list[dict[str, Any]],
]:
    grouped: dict[
        date,
        list[dict[str, Any]],
    ] = defaultdict(list)

    for row in rows:
        start = sap_date(
            row.get("startDate")
        )

        end = (
            sap_date(
                row.get("endDate")
            )
            or start
        )

        if (
            start is None
            or end is None
            or end < start
        ):
            continue

        item = {
            "requestId": str(
                row.get("requestID")
                or ""
            ),
            "statusId": str(
                row.get("statusID")
                or ""
            ),
            "statusText": str(
                row.get("statusTxt")
                or ""
            ),
            "statusClass": (
                leave_status(row)
            ),
            "absenceTypeCode": str(
                row.get(
                    "absenceTypeCode"
                )
                or ""
            ),
            "absenceTypeName": str(
                row.get(
                    "absenceTypeName"
                )
                or ""
            ),
            "startDate": (
                jalali_text(start)
            ),
            "endDate": (
                jalali_text(end)
            ),
            "plannedWorkingHours": (
                row.get(
                    "plannedWorkingHours"
                )
            ),
        }

        current = start

        while current <= end:
            grouped[current].append(
                item
            )

            current += timedelta(
                days=1
            )

    return dict(grouped)


def make_issue(
    kind: str,
    **details: Any,
) -> dict[str, Any]:
    return {
        "type": kind,
        "label": LABELS[kind],
        "details": details,
        "suggestedActions": [
            {
                "id": (
                    f"{kind.lower()}_"
                    f"{index + 1}"
                ),
                "label": label,
            }
            for index, label in enumerate(
                ACTIONS.get(
                    kind,
                    [],
                )
            )
        ],
    }


def analyze_day(
    day: date,
    events: list[dict[str, Any]],
    leaves: list[dict[str, Any]],
) -> dict[str, Any]:
    is_workday = (
        day.weekday()
        in WORKDAYS
    )

    active_leaves = [
        item
        for item in leaves
        if item["statusClass"]
        != "rejected"
    ]

    event_minutes = [
        int(item["minute"])
        for item in events
    ]

    entry: int | None = None
    exit_: int | None = None

    if len(event_minutes) == 1:
        only_event = (
            event_minutes[0]
        )

        if (
            only_event
            <= SINGLE_EVENT_ENTRY_LIMIT
        ):
            entry = only_event
        else:
            exit_ = only_event

    elif len(event_minutes) >= 2:
        entry = event_minutes[0]
        exit_ = event_minutes[-1]

    issues: list[
        dict[str, Any]
    ] = []

    if not is_workday:
        status = "NON_WORKING_DAY"
    else:
        status = "COMPLETE"

    if (
        is_workday
        and active_leaves
        and events
    ):
        status = "NEEDS_REVIEW"

        issues.append(
            make_issue(
                "LEAVE_ATTENDANCE_CONFLICT",
                leaveCount=len(
                    active_leaves
                ),
                eventCount=len(
                    events
                ),
            )
        )

    elif (
        is_workday
        and not events
    ):
        if not active_leaves:
            status = "NEEDS_REVIEW"

            issues.append(
                make_issue(
                    "POSSIBLE_ABSENCE"
                )
            )

        else:
            classes = {
                item["statusClass"]
                for item in active_leaves
            }

            if "pending" in classes:
                status = "NEEDS_REVIEW"

                issues.append(
                    make_issue(
                        "LEAVE_PENDING",
                        leaveCount=len(
                            active_leaves
                        ),
                    )
                )

            elif "unknown" in classes:
                status = "NEEDS_REVIEW"

                issues.append(
                    make_issue(
                        "LEAVE_STATUS_UNKNOWN",
                        leaveCount=len(
                            active_leaves
                        ),
                    )
                )

            else:
                status = "LEAVE"

    elif is_workday:
        if len(events) == 1:
            status = "NEEDS_REVIEW"

            if entry is not None:
                issues.append(
                    make_issue(
                        "MISSING_EXIT",
                        entryTime=(
                            clock_text(entry)
                        ),
                    )
                )

            else:
                issues.append(
                    make_issue(
                        "MISSING_ENTRY",
                        exitTime=(
                            clock_text(exit_)
                        ),
                    )
                )

        if (
            entry is not None
            and entry > ENTRY_LIMIT
        ):
            status = "NEEDS_REVIEW"

            late = (
                entry
                - (8 * 60)
            )

            issues.append(
                make_issue(
                    "LATE_ENTRY",
                    entryTime=(
                        clock_text(entry)
                    ),
                    allowedUntil="08:15",
                    lateMinutes=late,
                    lateText=(
                        duration_text(late)
                    ),
                )
            )

        if (
            exit_ is not None
            and exit_ < EXIT_STANDARD
        ):
            status = "NEEDS_REVIEW"

            early = (
                EXIT_STANDARD
                - exit_
            )

            issues.append(
                make_issue(
                    "EARLY_EXIT",
                    exitTime=(
                        clock_text(exit_)
                    ),
                    expectedExit="17:00",
                    earlyMinutes=early,
                    earlyText=(
                        duration_text(early)
                    ),
                )
            )

        if len(events) > 2:
            status = "NEEDS_REVIEW"

            issues.append(
                make_issue(
                    "EXTRA_EVENTS",
                    eventTimes=[
                        item["time"]
                        for item in events
                    ],
                )
            )

    return {
        "date": jalali_text(
            day
        ),
        "gregorianDate": (
            day.isoformat()
        ),
        "weekday": WEEKDAY_FA[
            day.weekday()
        ],
        "isWorkday": is_workday,
        "status": status,
        "expected": (
            {
                "entryWindow": (
                    "08:00 تا 08:15"
                ),
                "exitTime": "17:00",
            }
            if is_workday
            else None
        ),
        "actual": {
            "entryTime": (
                clock_text(entry)
            ),
            "exitTime": (
                clock_text(exit_)
            ),
            "eventCount": len(
                events
            ),
            "eventTimes": [
                item["time"]
                for item in events
            ],
        },
        "leaves": active_leaves,
        "issues": issues,
    }


def text_report(
    report: dict[str, Any],
) -> str:
    summary = report["summary"]

    lines = [
        "گزارش تحلیل تردد - نسخه آزمایشی",
        "=" * 42,
        (
            "بازه: "
            f"{report['period']['startDate']} "
            "تا "
            f"{report['period']['endDate']}"
        ),
        "",
        "قوانین:",
        "- روز کاری: شنبه تا چهارشنبه",
        "- ورود مجاز: 08:00 تا 08:15",
        (
            "- بعد از 08:15 "
            "تأخیر محاسبه می‌شود"
        ),
        "- خروج استاندارد: 17:00",
        (
            "- این تحلیل فقط‌خواندنی است "
            "و هیچ عملیاتی ثبت نمی‌کند"
        ),
        "",
        (
            "روز کاری بررسی‌شده: "
            f"{summary['workdayCount']}"
        ),
        (
            "روز کامل: "
            f"{summary['completeDayCount']}"
        ),
        (
            "روز نیازمند بررسی: "
            f"{summary['needsReviewDayCount']}"
        ),
        "",
        "جزئیات:",
    ]

    for day in report["days"]:
        if not day["isWorkday"]:
            continue

        actual = day["actual"]

        lines.append("")

        lines.append(
            (
                f"{day['weekday']} "
                f"{day['date']}"
            )
        )

        lines.append(
            (
                "  ورود: "
                f"{actual['entryTime'] or 'ثبت نشده'}"
            )
        )

        lines.append(
            (
                "  خروج: "
                f"{actual['exitTime'] or 'ثبت نشده'}"
            )
        )

        for leave in day["leaves"]:
            title = (
                leave[
                    "absenceTypeName"
                ]
                or leave[
                    "absenceTypeCode"
                ]
            )

            leave_status_text = (
                leave["statusId"]
                or leave[
                    "statusClass"
                ]
            )

            lines.append(
                (
                    f"  مرخصی: {title} "
                    f"({leave_status_text})"
                )
            )

        if not day["issues"]:
            lines.append(
                "  نتیجه: بدون مغایرت"
            )

        for item in day["issues"]:
            extra = ""

            if (
                item["type"]
                == "LATE_ENTRY"
            ):
                extra = (
                    " - "
                    + item["details"][
                        "lateText"
                    ]
                )

            elif (
                item["type"]
                == "EARLY_EXIT"
            ):
                extra = (
                    " - "
                    + item["details"][
                        "earlyText"
                    ]
                )

            lines.append(
                (
                    "  پیگیری: "
                    f"{item['label']}"
                    f"{extra}"
                )
            )

    lines.append("")
    lines.append(
        "تعداد مغایرت‌ها:"
    )

    for kind, count in sorted(
        summary[
            "issueCounts"
        ].items()
    ):
        lines.append(
            (
                f"- {LABELS.get(kind, kind)}: "
                f"{count}"
            )
        )

    return (
        "\n".join(lines)
        + "\n"
    )


def main() -> None:
    if len(sys.argv) != 3:
        print(
            "USAGE: "
            "monthly_attendance_analyzer_v1.py "
            "START_DATE END_DATE"
        )

        print(
            "EXAMPLE: "
            "monthly_attendance_analyzer_v1.py "
            "1405/05/01 1405/05/07"
        )

        raise SystemExit(2)

    start_text = (
        sys.argv[1].strip()
    )

    end_text = (
        sys.argv[2].strip()
    )

    start = jalali_to_gregorian(
        *parse_jalali(
            start_text
        )
    )

    end = jalali_to_gregorian(
        *parse_jalali(
            end_text
        )
    )

    if end < start:
        raise ValueError(
            "تاریخ پایان قبل از تاریخ شروع است."
        )

    safe_start = (
        start_text.replace(
            "/",
            "-",
        )
    )

    safe_end = (
        end_text.replace(
            "/",
            "-",
        )
    )

    probe_dir = (
        ROOT
        / "probe_outputs"
    )

    time_file = (
        probe_dir
        / (
            "get_time_event_"
            f"{safe_start}_"
            f"{safe_end}.json"
        )
    )

    leave_file = (
        probe_dir
        / (
            "get_leave_request_"
            f"{safe_start}.json"
        )
    )

    events = group_events(
        load_rows(
            time_file
        )
    )

    leaves = group_leaves(
        load_rows(
            leave_file
        )
    )

    days: list[
        dict[str, Any]
    ] = []

    current = start

    while current <= end:
        days.append(
            analyze_day(
                current,
                events.get(
                    current,
                    [],
                ),
                leaves.get(
                    current,
                    [],
                ),
            )
        )

        current += timedelta(
            days=1
        )

    issue_counts: Counter[str] = (
        Counter()
    )

    for day in days:
        for item in day["issues"]:
            issue_counts[
                item["type"]
            ] += 1

    workdays = [
        day
        for day in days
        if day["isWorkday"]
    ]

    report = {
        "version": "1.0",
        "mode": (
            "offline-read-only"
        ),
        "period": {
            "startDate": (
                jalali_text(start)
            ),
            "endDate": (
                jalali_text(end)
            ),
        },
        "rules": {
            "workdays": [
                "شنبه",
                "یکشنبه",
                "دوشنبه",
                "سه‌شنبه",
                "چهارشنبه",
            ],
            "entryWindow": (
                "08:00 تا 08:15"
            ),
            "lateAfter": "08:15",
            "expectedExit": "17:00",
        },
        "summary": {
            "calendarDayCount": len(
                days
            ),
            "workdayCount": len(
                workdays
            ),
            "completeDayCount": sum(
                day["status"]
                == "COMPLETE"
                for day in workdays
            ),
            "leaveDayCount": sum(
                day["status"]
                == "LEAVE"
                for day in workdays
            ),
            "needsReviewDayCount": sum(
                day["status"]
                == "NEEDS_REVIEW"
                for day in workdays
            ),
            "issueCounts": dict(
                sorted(
                    issue_counts.items()
                )
            ),
        },
        "days": days,
        "sourceFiles": {
            "timeEvents": str(
                time_file
            ),
            "leaveRequests": str(
                leave_file
            ),
        },
    }

    output_dir = (
        ROOT
        / "monthly_attendance_outputs"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    base = (
        "monthly_attendance_"
        f"{safe_start}_"
        f"{safe_end}"
    )

    json_output = (
        output_dir
        / f"{base}.json"
    )

    text_output = (
        output_dir
        / f"{base}.txt"
    )

    json_output.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    text_output.write_text(
        text_report(
            report
        ),
        encoding="utf-8",
    )

    print("ANALYSIS_OK")
    print(
        "MODE=offline-read-only"
    )

    print(
        "WORKDAY_COUNT="
        f"{report['summary']['workdayCount']}"
    )

    print(
        "COMPLETE_DAY_COUNT="
        f"{report['summary']['completeDayCount']}"
    )

    print(
        "NEEDS_REVIEW_DAY_COUNT="
        f"{report['summary']['needsReviewDayCount']}"
    )

    print(
        "ISSUE_COUNTS="
        + json.dumps(
            report[
                "summary"
            ][
                "issueCounts"
            ],
            ensure_ascii=False,
            sort_keys=True,
        )
    )

    print(
        f"JSON_OUTPUT={json_output}"
    )

    print(
        f"TEXT_OUTPUT={text_output}"
    )


if __name__ == "__main__":
    main()