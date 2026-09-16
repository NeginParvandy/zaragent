from __future__ import annotations

import importlib
import py_compile
import sys
import traceback
from pathlib import Path


ROOT = Path(r"D:\serviceAi")

DEMO_FILE = (
    ROOT
    / "app"
    / "application"
    / "services"
    / "monthly_attendance_chat_demo.py"
)

CHAT_FILE = (
    ROOT
    / "app"
    / "application"
    / "services"
    / "chat_service.py"
)

BACKUP_FILE = DEMO_FILE.with_name(
    "monthly_attendance_chat_demo.py."
    "bak_before_hr_commit_v1"
)

MARKER = "MONTHLY_ATTENDANCE_HR_COMMIT_V1"


original_bytes = DEMO_FILE.read_bytes()


HELPER_SOURCE = r'''
# MONTHLY_ATTENDANCE_HR_COMMIT_V1
CONVERSATION_STATE = "conversation"
CONVERSATION_STATE_TTL_MINUTES = 30


def _clock_minutes(
    value: str,
) -> int:
    match = re.fullmatch(
        r"(\d{1,2}):(\d{2})",
        str(value or "").strip(),
    )

    if not match:
        raise ValueError(
            "ساعت مرخصی ساعتی معتبر نیست."
        )

    hour = int(match.group(1))
    minute = int(match.group(2))

    if (
        not 0 <= hour <= 23
        or not 0 <= minute <= 59
    ):
        raise ValueError(
            "ساعت مرخصی ساعتی معتبر نیست."
        )

    return hour * 60 + minute


def _hourly_leave_payload_from_decision(
    decision: dict[str, Any],
) -> dict[str, Any] | None:
    if (
        str(
            decision.get("command")
            or ""
        ).strip()
        != "CLAIM_HOURLY_LEAVE"
    ):
        return None

    date_text = str(
        decision.get("date")
        or ""
    ).strip()

    label = str(
        decision.get("label")
        or ""
    ).strip()

    match = re.search(
        r"از\s*"
        r"(\d{1,2}:\d{2})"
        r"\s*تا\s*"
        r"(\d{1,2}:\d{2})",
        label,
    )

    if not date_text or not match:
        raise ValueError(
            "تاریخ یا ساعت مرخصی ساعتی کامل نیست."
        )

    start_time = match.group(1)
    end_time = match.group(2)

    start_minutes = _clock_minutes(
        start_time
    )

    end_minutes = _clock_minutes(
        end_time
    )

    if end_minutes <= start_minutes:
        raise ValueError(
            "ساعت پایان باید بعد از ساعت شروع باشد."
        )

    return {
        "absenceTypeCode": "0080",
        "startDate": date_text,
        "endDate": date_text,
        "startTime": start_time,
        "endTime": end_time,
        "notes": (
            "ثبت از طریق بررسی گزارش ماهانه تردد"
        ),
        "additionalValues": {},
    }


async def _save_pending_action_to_conversation(
    context: Any,
    action: dict[str, Any],
    action_payload: dict[str, Any],
) -> None:
    from app.application.container import (
        get_container,
    )

    container = get_container()

    employee_id = str(
        getattr(
            context,
            "employee_id",
            "",
        )
        or ""
    ).strip()

    conversation_id = str(
        getattr(
            context,
            "conversation_id",
            "",
        )
        or ""
    ).strip()

    if not employee_id:
        raise ValueError(
            "کد پرسنلی برای ثبت عملیات مشخص نیست."
        )

    existing_state = await asyncio.to_thread(
        container.repository.get_chat_state,
        employee_id,
        conversation_id or None,
    )

    conversation_payload: dict[str, Any] = {}

    if isinstance(
        existing_state,
        dict,
    ):
        existing_payload = (
            existing_state.get("payload")
        )

        if isinstance(
            existing_payload,
            dict,
        ):
            conversation_payload = dict(
                existing_payload
            )

    conversation_payload[
        "pendingActionId"
    ] = str(
        action.get("id")
        or ""
    )

    conversation_payload["proposal"] = {
        "actionType": "CREATE_LEAVE",
        "data": action_payload,
        "reply": (
            "ثبت مرخصی ساعتی از "
            f"{action_payload['startTime']} "
            "تا "
            f"{action_payload['endTime']} "
            "برای "
            f"{action_payload['startDate']} "
            "آماده تأیید است."
        ),
    }

    await asyncio.to_thread(
        container.repository.save_chat_state,
        employee_id,
        CONVERSATION_STATE,
        conversation_payload,
        CONVERSATION_STATE_TTL_MINUTES,
        conversation_id or None,
    )


async def _create_hourly_leave_pending_action(
    context: Any,
    decision: dict[str, Any],
) -> dict[str, Any] | None:
    action_payload = (
        _hourly_leave_payload_from_decision(
            decision
        )
    )

    if action_payload is None:
        return None

    from app.application.container import (
        get_container,
    )

    container = get_container()

    employee_id = str(
        getattr(
            context,
            "employee_id",
            "",
        )
        or ""
    ).strip()

    if not employee_id:
        raise ValueError(
            "کد پرسنلی برای ثبت عملیات مشخص نیست."
        )

    action = (
        await container.action_service
        .create_pending_action(
            employee_id,
            "CREATE_LEAVE",
            action_payload,
        )
    )

    await _save_pending_action_to_conversation(
        context,
        action,
        action_payload,
    )

    decision[
        "decisionStatus"
    ] = "AWAITING_CONFIRMATION"

    decision[
        "pendingActionId"
    ] = action.get("id")

    return {
        "action": action,
        "payload": action_payload,
    }


def _pending_leave_response(
    state: dict[str, Any],
    decision: dict[str, Any],
    pending: dict[str, Any],
) -> dict[str, Any]:
    action = pending["action"]
    payload = pending["payload"]

    return {
        "reply": (
            "بررسی گزارش ماهانه تمام شد.\n\n"
            "مرخصی ساعتی زیر آماده ثبت واقعی است:\n"
            f"- تاریخ: {payload['startDate']}\n"
            f"- از ساعت {payload['startTime']} "
            f"تا {payload['endTime']}\n\n"
            "برای ثبت در سامانه منابع انسانی "
            "«تأیید» را بفرستید."
        ),
        "requiresConfirmation": True,
        "pendingAction": {
            "id": action["id"],
            "label": (
                "تأیید و ثبت مرخصی ساعتی"
            ),
            "expiresAt": action.get(
                "expiresAt"
            ),
        },
        "suggestions": [
            "تأیید",
            "لغو",
        ],
        "data": {
            "feature": (
                "monthlyAttendanceReview"
            ),
            "workflowId": state.get(
                "workflowId"
            ),
            "workflowStatus": state.get(
                "status"
            ),
            "decision": decision,
            "pendingActionId": action.get(
                "id"
            ),
            "writesToHr": False,
            "writesToHrAfterConfirmation": True,
        },
    }
'''


try:
    source = original_bytes.decode(
        "utf-8-sig"
    )

    if MARKER in source:
        print(
            "PATCH_ALREADY_APPLIED"
        )
        raise SystemExit(0)

    if not BACKUP_FILE.exists():
        BACKUP_FILE.write_bytes(
            original_bytes
        )

    if "import asyncio" not in source:
        import_anchor = "import hashlib"

        if source.count(
            import_anchor
        ) != 1:
            raise RuntimeError(
                "ASYNCIO_IMPORT_ANCHOR_NOT_FOUND"
            )

        source = source.replace(
            import_anchor,
            (
                "import asyncio\n"
                + import_anchor
            ),
            1,
        )

    function_anchor = (
        "\nasync def "
        "handle_monthly_attendance_demo("
    )

    if source.count(
        function_anchor
    ) != 1:
        raise RuntimeError(
            "HANDLER_ANCHOR_NOT_FOUND_OR_DUPLICATED"
        )

    source = source.replace(
        function_anchor,
        (
            "\n"
            + HELPER_SOURCE.strip()
            + "\n\n"
            + function_anchor.lstrip("\n")
        ),
        1,
    )

    response_start_anchor = (
        "response = _next_response("
    )

    cache_anchor = (
        "_cache_response("
    )

    response_match = source.rfind(
        response_start_anchor
    )

    response_start = source.rfind(
        "\n",
        0,
        response_match,
    ) + 1

    if response_start < 0:
        raise RuntimeError(
            "RESPONSE_START_NOT_FOUND"
        )

    cache_start = source.find(
        cache_anchor,
        response_start,
    )

    if cache_start < 0:
        raise RuntimeError(
            "CACHE_ANCHOR_NOT_FOUND"
        )

    current_response_block = source[
        response_start:cache_start
    ]

    if (
        current_response_block.count(
            "_next_response("
        )
        != 1
    ):
        raise RuntimeError(
            "RESPONSE_BLOCK_AMBIGUOUS"
        )

    new_response_block = '''        pending_leave = (
            await _create_hourly_leave_pending_action(
                context,
                decision,
            )
        )

        if pending_leave is not None:
            response = _pending_leave_response(
                existing_state,
                decision,
                pending_leave,
            )
        else:
            response = _next_response(
                cards_payload,
                existing_state,
                selected_label,
            )

'''

    source = (
        source[:response_start]
        + new_response_block
        + source[cache_start:]
    )

    DEMO_FILE.write_text(
        source,
        encoding="utf-8",
    )

    py_compile.compile(
        str(DEMO_FILE),
        doraise=True,
    )

    py_compile.compile(
        str(CHAT_FILE),
        doraise=True,
    )

    if str(ROOT) not in sys.path:
        sys.path.insert(
            0,
            str(ROOT),
        )

    importlib.invalidate_caches()

    module_name = (
        "app.application.services."
        "monthly_attendance_chat_demo"
    )

    sys.modules.pop(
        module_name,
        None,
    )

    module = importlib.import_module(
        module_name
    )

    test_payload = (
        module
        ._hourly_leave_payload_from_decision(
            {
                "command": (
                    "CLAIM_HOURLY_LEAVE"
                ),
                "date": "1405/05/07",
                "label": (
                    "ثبت مرخصی ساعتی "
                    "از 08:00 تا 11:00"
                ),
            }
        )
    )

    expected = {
        "absenceTypeCode": "0080",
        "startDate": "1405/05/07",
        "endDate": "1405/05/07",
        "startTime": "08:00",
        "endTime": "11:00",
    }

    for key, value in expected.items():
        if test_payload.get(key) != value:
            raise RuntimeError(
                "HOURLY_LEAVE_PAYLOAD_TEST_FAILED"
            )

    print("PATCH_OK")
    print("SOURCE_SYNTAX_OK=True")
    print(
        "HOURLY_LEAVE_PENDING_ACTION_TEST_OK"
    )
    print("API_ROUTES_CHANGED=False")
    print(
        f"BACKUP={BACKUP_FILE}"
    )

except SystemExit:
    raise

except Exception:
    DEMO_FILE.write_bytes(
        original_bytes
    )

    print(
        "PATCH_FAILED_ROLLED_BACK"
    )

    traceback.print_exc()
    raise