from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(r"D:\serviceAi")


ISSUE_UI: dict[str, dict[str, str]] = {
    "POSSIBLE_ABSENCE": {
        "title": "غیبت احتمالی",
        "severity": "high",
        "description": (
            "برای این روز هیچ ورود، خروج یا "
            "مرخصی فعالی پیدا نشد."
        ),
    },
    "MISSING_ENTRY": {
        "title": "ورود ثبت نشده",
        "severity": "high",
        "description": (
            "خروج ثبت شده است، اما ورود "
            "برای این روز پیدا نشد."
        ),
    },
    "MISSING_EXIT": {
        "title": "خروج ثبت نشده",
        "severity": "high",
        "description": (
            "ورود ثبت شده است، اما خروج "
            "برای این روز پیدا نشد."
        ),
    },
    "LATE_ENTRY": {
        "title": "تأخیر ورود",
        "severity": "medium",
        "description": (
            "زمان ورود بعد از محدوده مجاز "
            "08:00 تا 08:15 بوده است."
        ),
    },
    "EARLY_EXIT": {
        "title": "خروج زودهنگام",
        "severity": "medium",
        "description": (
            "زمان خروج قبل از ساعت استاندارد "
            "17:00 بوده است."
        ),
    },
    "EXTRA_EVENTS": {
        "title": "ترددهای اضافی",
        "severity": "medium",
        "description": (
            "بیش از دو رویداد تردد برای این "
            "روز پیدا شده و نیازمند بررسی است."
        ),
    },
    "LEAVE_ATTENDANCE_CONFLICT": {
        "title": "تداخل مرخصی و تردد",
        "severity": "high",
        "description": (
            "برای این روز هم درخواست مرخصی "
            "و هم رویداد تردد وجود دارد."
        ),
    },
    "LEAVE_PENDING": {
        "title": "مرخصی در انتظار تعیین وضعیت",
        "severity": "medium",
        "description": (
            "درخواست مرخصی ثبت شده، اما وضعیت "
            "نهایی آن هنوز مشخص نیست."
        ),
    },
        "LEAVE_STATUS_UNKNOWN": {
        "title": "وضعیت نامشخص مرخصی",
        "severity": "medium",
        "description": (
            "وضعیت درخواست مرخصی توسط موتور "
            "تحلیل شناخته نشد."
        ),
    },
}

ACTION_CODES: dict[str, str] = {
    "در محل کار بودم": "CLAIM_PRESENT",
    "مرخصی داشتم": "CLAIM_LEAVE",
    "مرخصی ساعتی داشتم": "CLAIM_HOURLY_LEAVE",
    "ثبت مرخصی ساعتی از 08:00 تا 11:00": "CLAIM_HOURLY_LEAVE",
    "مأموریت بودم": "CLAIM_MISSION",
    "غیبت درست است": "ACCEPT_ABSENCE",
    "اطلاعات درست است": "ACCEPT_CURRENT_DATA",
    "تأخیر درست است": "ACCEPT_LATE_ENTRY",
    "خروج زودهنگام درست است": "ACCEPT_EARLY_EXIT",
    "ثبت ورود": "REQUEST_ENTRY_CORRECTION",
    "ثبت خروج": "REQUEST_EXIT_CORRECTION",
    "ثبت ورود را فراموش کردم": (
        "REQUEST_ENTRY_CORRECTION"
    ),
    "ثبت خروج اشتباه است": (
        "REQUEST_EXIT_CORRECTION"
    ),
    "مرخصی درست است": "CONFIRM_LEAVE",
    "وضعیت درخواست را بررسی کن": (
        "CHECK_LEAVE_STATUS"
    ),
}


NEXT_STEPS: dict[str, str] = {
    "CLAIM_PRESENT": "collect_attendance_details",
    "CLAIM_LEAVE": "collect_leave_details",
    "CLAIM_HOURLY_LEAVE": "collect_leave_details",
    "CLAIM_MISSION": "collect_mission_details",
    "ACCEPT_ABSENCE": "resolve_without_correction",
    "ACCEPT_CURRENT_DATA": "resolve_without_correction",
    "ACCEPT_LATE_ENTRY": "resolve_without_correction",
    "ACCEPT_EARLY_EXIT": "resolve_without_correction",
    "REQUEST_ENTRY_CORRECTION": (
        "collect_missing_entry_time"
    ),
    "REQUEST_EXIT_CORRECTION": (
        "collect_missing_exit_time"
    ),
    "CONFIRM_LEAVE": "review_leave_conflict",
    "CHECK_LEAVE_STATUS": "fetch_leave_status",
}


MUTATION_CANDIDATES = {
    "CLAIM_PRESENT",
    "CLAIM_LEAVE",
    "CLAIM_HOURLY_LEAVE",
    "CLAIM_MISSION",
    "REQUEST_ENTRY_CORRECTION",
    "REQUEST_EXIT_CORRECTION",
}


def load_json(
    path: Path,
) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(
            f"فایل گزارش پیدا نشد: {path}"
        )

    payload = json.loads(
        path.read_text(
            encoding="utf-8-sig"
        )
    )

    if not isinstance(payload, dict):
        raise ValueError(
            "ساختار گزارش باید JSON Object باشد."
        )

    return payload


def safe_text(
    value: Any,
    fallback: str = "",
) -> str:
    text = str(
        value
        if value is not None
        else ""
    ).strip()

    return text or fallback


def safe_int(
    value: Any,
    fallback: int = 0,
) -> int:
    try:
        return int(value)

    except (
        TypeError,
        ValueError,
    ):
        return fallback


def slug(
    value: str,
) -> str:
    cleaned = re.sub(
        r"[^A-Za-z0-9]+",
        "-",
        value,
    )

    return cleaned.strip(
        "-"
    ).lower()


def display_time(
    value: Any,
) -> str:
    return safe_text(
        value,
        "ثبت نشده",
    )


def build_leave_text(
    leaves: list[dict[str, Any]],
) -> str:
    if not leaves:
        return "ندارد"

    parts: list[str] = []

    for leave in leaves:
        name = safe_text(
            leave.get("absenceTypeName"),
            safe_text(
                leave.get("absenceTypeCode"),
                "نوع نامشخص",
            ),
        )

        status = safe_text(
            leave.get("statusId"),
            safe_text(
                leave.get("statusClass"),
                "وضعیت نامشخص",
            ),
        )

        parts.append(
            f"{name} ({status})"
        )

    return "، ".join(parts)


def build_facts(
    day: dict[str, Any],
) -> list[dict[str, str]]:
    actual = day.get("actual")

    if not isinstance(actual, dict):
        actual = {}

    leaves = day.get("leaves")

    if not isinstance(leaves, list):
        leaves = []

    return [
        {
            "label": "تاریخ",
            "value": safe_text(
                day.get("date"),
                "-",
            ),
        },
        {
            "label": "روز",
            "value": safe_text(
                day.get("weekday"),
                "-",
            ),
        },
        {
            "label": "ورود",
            "value": display_time(
                actual.get("entryTime")
            ),
        },
        {
            "label": "خروج",
            "value": display_time(
                actual.get("exitTime")
            ),
        },
        {
            "label": "ساعت کاری",
            "value": (
                "ورود 08:00 تا 08:15، "
                "خروج 17:00"
            ),
        },
        {
            "label": "مرخصی",
            "value": build_leave_text(
                [
                    item
                    for item in leaves
                    if isinstance(
                        item,
                        dict,
                    )
                ]
            ),
        },
    ]


def build_issue_description(
    issue_type: str,
    details: dict[str, Any],
) -> str:
    ui = ISSUE_UI.get(
        issue_type,
        {
            "description": (
                "این مورد نیازمند بررسی کاربر است."
            )
        },
    )

    base = safe_text(
        ui.get("description"),
        "این مورد نیازمند بررسی است.",
    )

    if issue_type == "LATE_ENTRY":
        entry_time = safe_text(
            details.get("entryTime"),
            "نامشخص",
        )

        late_text = safe_text(
            details.get("lateText"),
            "مدت نامشخص",
        )

        return (
            f"ورود ساعت {entry_time} ثبت شده؛ "
            f"میزان تأخیر {late_text} است."
        )

    if issue_type == "EARLY_EXIT":
        exit_time = safe_text(
            details.get("exitTime"),
            "نامشخص",
        )

        early_text = safe_text(
            details.get("earlyText"),
            "مدت نامشخص",
        )

        return (
            f"خروج ساعت {exit_time} ثبت شده؛ "
            f"میزان خروج زودهنگام "
            f"{early_text} است."
        )

    if issue_type == "MISSING_ENTRY":
        exit_time = safe_text(
            details.get("exitTime"),
            "نامشخص",
        )

        return (
            "ورود ثبت نشده، اما خروج ساعت "
            f"{exit_time} وجود دارد."
        )

    if issue_type == "MISSING_EXIT":
        entry_time = safe_text(
            details.get("entryTime"),
            "نامشخص",
        )

        return (
            "ورود ساعت "
            f"{entry_time} ثبت شده، "
            "اما خروج وجود ندارد."
        )

    return base


def build_action(
    *,
    workflow_id: str,
    card_id: str,
    period: dict[str, Any],
    day: dict[str, Any],
    issue_type: str,
    source_action: dict[str, Any],
    action_index: int,
) -> dict[str, Any]:
    label = safe_text(
        source_action.get("label"),
        f"گزینه {action_index}",
    )

    resolution_code = ACTION_CODES.get(
        label,
        safe_text(
            source_action.get("id"),
            f"OPTION_{action_index}",
        ).upper(),
    )

    action_id = (
        f"{card_id}-action-"
        f"{action_index:02d}"
    )

    may_lead_to_mutation = (
        resolution_code
        in MUTATION_CANDIDATES
    )

    return {
        "actionId": action_id,
        "label": label,
        "interactionType": "quick_reply",
        "command": resolution_code,
        "nextStep": NEXT_STEPS.get(
            resolution_code,
            "review_selection",
        ),
        "writesImmediately": False,
        "mayLeadToMutation": (
            may_lead_to_mutation
        ),
        "requiresPreviewBeforeMutation": (
            may_lead_to_mutation
        ),
        "requiresExplicitConfirmation": (
            may_lead_to_mutation
        ),
        "payload": {
            "workflowId": workflow_id,
            "cardId": card_id,
            "period": {
                "startDate": safe_text(
                    period.get("startDate")
                ),
                "endDate": safe_text(
                    period.get("endDate")
                ),
            },
            "date": safe_text(
                day.get("date")
            ),
            "weekday": safe_text(
                day.get("weekday")
            ),
            "issueType": issue_type,
            "resolutionCode": (
                resolution_code
            ),
        },
    }


def build_issue_card(
    *,
    workflow_id: str,
    period: dict[str, Any],
    day: dict[str, Any],
    issue: dict[str, Any],
    card_number: int,
    total_cards: int,
    issue_number_for_day: int,
) -> dict[str, Any]:
    issue_type = safe_text(
        issue.get("type"),
        "UNKNOWN",
    ).upper()

    ui = ISSUE_UI.get(
        issue_type,
        {
            "title": safe_text(
                issue.get("label"),
                "مورد نیازمند بررسی",
            ),
            "severity": "medium",
            "description": (
                "این مورد نیازمند بررسی کاربر است."
            ),
        },
    )

    date_text = safe_text(
        day.get("date"),
        "unknown-date",
    )

    card_id = (
        "attendance-"
        f"{slug(date_text)}-"
        f"{slug(issue_type)}-"
        f"{issue_number_for_day:02d}"
    )

    details = issue.get("details")

    if not isinstance(details, dict):
        details = {}

    source_actions = issue.get(
        "suggestedActions"
    )

    if not isinstance(
        source_actions,
        list,
    ):
        source_actions = []

    actions = [
        build_action(
            workflow_id=workflow_id,
            card_id=card_id,
            period=period,
            day=day,
            issue_type=issue_type,
            source_action=action,
            action_index=index,
        )
        for index, action in enumerate(
            (
                item
                for item in source_actions
                if isinstance(
                    item,
                    dict,
                )
            ),
            start=1,
        )
    ]

    return {
        "cardId": card_id,
        "cardType": "attendance_issue",
        "position": card_number,
        "total": total_cards,
        "progressText": (
            f"مورد {card_number} "
            f"از {total_cards}"
        ),
        "severity": safe_text(
            ui.get("severity"),
            "medium",
        ),
        "title": safe_text(
            ui.get("title"),
            safe_text(
                issue.get("label"),
                "نیازمند بررسی",
            ),
        ),
        "subtitle": (
            f"{safe_text(day.get('weekday'), '')} "
            f"{date_text}"
        ).strip(),
        "description": (
            build_issue_description(
                issue_type,
                details,
            )
        ),
        "facts": build_facts(
            day
        ),
        "details": details,
        "interaction": {
            "mode": "single_choice",
            "prompt": (
                "کدام گزینه وضعیت واقعی "
                "این روز را توضیح می‌دهد؟"
            ),
            "actions": actions,
        },
        "policy": {
            "requiresHrAuthentication": True,
            "selectionWritesToHr": False,
            "correctionRequiresPreview": True,
            "correctionRequiresConfirmation": True,
        },
    }


def collect_issue_cards(
    *,
    report: dict[str, Any],
    workflow_id: str,
) -> list[dict[str, Any]]:
    period = report.get("period")

    if not isinstance(period, dict):
        period = {}

    days = report.get("days")

    if not isinstance(days, list):
        days = []

    raw_items: list[
        tuple[
            dict[str, Any],
            dict[str, Any],
            int,
        ]
    ] = []

    for day in days:
        if not isinstance(day, dict):
            continue

        issues = day.get("issues")

        if not isinstance(issues, list):
            continue

        issue_number_for_day = 0

        for issue in issues:
            if not isinstance(issue, dict):
                continue

            issue_number_for_day += 1

            raw_items.append(
                (
                    day,
                    issue,
                    issue_number_for_day,
                )
            )

    total_cards = len(
        raw_items
    )

    cards: list[
        dict[str, Any]
    ] = []

    for card_number, item in enumerate(
        raw_items,
        start=1,
    ):
        day, issue, issue_number = item

        cards.append(
            build_issue_card(
                workflow_id=workflow_id,
                period=period,
                day=day,
                issue=issue,
                card_number=card_number,
                total_cards=total_cards,
                issue_number_for_day=(
                    issue_number
                ),
            )
        )

    return cards


def build_summary_card(
    *,
    workflow_id: str,
    period: dict[str, Any],
    summary: dict[str, Any],
    issue_cards: list[dict[str, Any]],
) -> dict[str, Any]:
    workday_count = safe_int(
        summary.get("workdayCount")
    )

    complete_count = safe_int(
        summary.get("completeDayCount")
    )

    review_count = safe_int(
        summary.get(
            "needsReviewDayCount"
        )
    )

    issue_count = len(
        issue_cards
    )

    if issue_count:
        title = (
            "گزارش تردد آماده بررسی است"
        )

        body = (
            f"{workday_count} روز کاری بررسی شد؛ "
            f"{complete_count} روز بدون مغایرت و "
            f"{review_count} روز نیازمند بررسی است. "
            f"در مجموع {issue_count} مورد "
            "باید با شما مرور شود."
        )

        actions = [
            {
                "actionId": (
                    "start-monthly-attendance-review"
                ),
                "label": "شروع بررسی",
                "interactionType": "primary",
                "command": "START_REVIEW",
                "writesImmediately": False,
                "payload": {
                    "workflowId": workflow_id,
                    "firstCardId": (
                        issue_cards[0][
                            "cardId"
                        ]
                    ),
                },
            },
            {
                "actionId": (
                    "view-monthly-attendance-details"
                ),
                "label": "مشاهده جزئیات گزارش",
                "interactionType": "secondary",
                "command": "VIEW_REPORT",
                "writesImmediately": False,
                "payload": {
                    "workflowId": workflow_id,
                },
            },
        ]

    else:
        title = (
            "گزارش تردد بدون مغایرت است"
        )

        body = (
            f"{workday_count} روز کاری بررسی شد "
            "و مورد نیازمند پیگیری پیدا نشد."
        )

        actions = [
            {
                "actionId": (
                    "close-monthly-attendance-report"
                ),
                "label": "بستن گزارش",
                "interactionType": "primary",
                "command": "CLOSE_REPORT",
                "writesImmediately": False,
                "payload": {
                    "workflowId": workflow_id,
                },
            }
        ]

    return {
        "cardId": "monthly-attendance-summary",
        "cardType": "attendance_summary",
        "title": title,
        "body": body,
        "periodText": (
            f"{safe_text(period.get('startDate'), '-')}"
            " تا "
            f"{safe_text(period.get('endDate'), '-')}"
        ),
        "metrics": [
            {
                "label": "روز کاری",
                "value": workday_count,
            },
            {
                "label": "روز بدون مغایرت",
                "value": complete_count,
            },
            {
                "label": "روز نیازمند بررسی",
                "value": review_count,
            },
            {
                "label": "تعداد موارد",
                "value": issue_count,
            },
        ],
        "actions": actions,
    }


def build_text_preview(
    payload: dict[str, Any],
) -> str:
    summary_card = payload[
        "presentation"
    ][
        "summaryCard"
    ]

    issue_cards = payload[
        "presentation"
    ][
        "issueCards"
    ]

    lines = [
        "پیش‌نمایش کارت‌های گزارش تردد",
        "=" * 42,
        "",
        summary_card["title"],
        summary_card["body"],
        "",
    ]

    for card in issue_cards:
        lines.extend(
            [
                "-" * 42,
                card["progressText"],
                card["title"],
                card["subtitle"],
                card["description"],
                "",
                "اطلاعات:",
            ]
        )

        for fact in card["facts"]:
            lines.append(
                f"- {fact['label']}: "
                f"{fact['value']}"
            )

        lines.append("")
        lines.append(
            card[
                "interaction"
            ][
                "prompt"
            ]
        )

        for action in card[
            "interaction"
        ][
            "actions"
        ]:
            lines.append(
                f"[ {action['label']} ]"
            )

        lines.append("")

    lines.extend(
        [
            "-" * 42,
            (
                "هیچ‌کدام از انتخاب‌های این "
                "پیش‌نمایش مستقیماً اطلاعات "
                "منابع انسانی را تغییر نمی‌دهند."
            ),
            (
                "هر اصلاح احتمالی باید ابتدا "
                "نمایش داده شود و سپس با تأیید "
                "صریح کاربر اجرا شود."
            ),
        ]
    )

    return (
        "\n".join(lines)
        + "\n"
    )


def main() -> None:
    if len(sys.argv) != 3:
        print(
            "USAGE: "
            "monthly_attendance_card_builder_v1.py "
            "START_DATE END_DATE"
        )

        print(
            "EXAMPLE: "
            "monthly_attendance_card_builder_v1.py "
            "1405/05/01 1405/05/07"
        )

        raise SystemExit(2)

    start_date = sys.argv[1].strip()
    end_date = sys.argv[2].strip()

    safe_start = start_date.replace(
        "/",
        "-",
    )

    safe_end = end_date.replace(
        "/",
        "-",
    )

    input_file = (
        ROOT
        / "monthly_attendance_outputs"
        / (
            "monthly_attendance_"
            f"{safe_start}_"
            f"{safe_end}.json"
        )
    )

    report = load_json(
        input_file
    )

    period = report.get("period")

    if not isinstance(period, dict):
        period = {
            "startDate": start_date,
            "endDate": end_date,
        }

    summary = report.get("summary")

    if not isinstance(summary, dict):
        summary = {}

    workflow_id = (
        "monthly-attendance-"
        f"{safe_start}-"
        f"{safe_end}"
    )

    issue_cards = collect_issue_cards(
        report=report,
        workflow_id=workflow_id,
    )

    summary_card = build_summary_card(
        workflow_id=workflow_id,
        period=period,
        summary=summary,
        issue_cards=issue_cards,
    )

    issue_counts = Counter(
        safe_text(
            card.get("title"),
            "نامشخص",
        )
        for card in issue_cards
    )

    output_payload = {
        "version": "1.0",
        "workflowId": workflow_id,
        "workflowType": (
            "monthly_attendance_review"
        ),
        "generatedAtUtc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
        "mode": "presentation-only",
        "sourceReport": str(
            input_file
        ),
        "period": period,
        "reviewPolicy": {
            "presentationMode": (
                "guided_one_issue_at_a_time"
            ),
            "selectionWritesToHr": False,
            "automaticCorrectionAllowed": False,
            "mutationRequiresPreview": True,
            "mutationRequiresExplicitConfirmation": (
                True
            ),
            "idempotencyRequired": True,
            "auditLogRequired": True,
        },
        "statistics": {
            "issueCardCount": len(
                issue_cards
            ),
            "issueCountsByTitle": dict(
                sorted(
                    issue_counts.items()
                )
            ),
        },
        "presentation": {
            "summaryCard": summary_card,
            "issueCards": issue_cards,
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

    base_name = (
        "monthly_attendance_cards_"
        f"{safe_start}_"
        f"{safe_end}"
    )

    json_output = (
        output_dir
        / f"{base_name}.json"
    )

    text_output = (
        output_dir
        / f"{base_name}.txt"
    )

    json_output.write_text(
        json.dumps(
            output_payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    text_output.write_text(
        build_text_preview(
            output_payload
        ),
        encoding="utf-8",
    )

    print("CARD_BUILD_OK")
    print("MODE=presentation-only")
    print(
        "ISSUE_CARD_COUNT="
        f"{len(issue_cards)}"
    )

    print(
        "JSON_OUTPUT="
        f"{json_output}"
    )

    print(
        "TEXT_OUTPUT="
        f"{text_output}"
    )


if __name__ == "__main__":
    main()