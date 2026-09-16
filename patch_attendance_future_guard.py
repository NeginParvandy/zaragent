# -*- coding: utf-8 -*-

from __future__ import annotations

import asyncio
import importlib
import py_compile
import shutil
import sys
import traceback
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(r"D:\serviceAi")

CHAT = (
    ROOT
    / "app"
    / "application"
    / "services"
    / "chat_service.py"
)

ACTION = (
    ROOT
    / "app"
    / "application"
    / "services"
    / "action_service.py"
)

CHAT_BACKUP = CHAT.with_name(
    "chat_service.py.bak_before_attendance_future_guard"
)

ACTION_BACKUP = ACTION.with_name(
    "action_service.py.bak_before_attendance_future_guard"
)

CHAT_MARKER = (
    "# ATTENDANCE_FUTURE_CHAT_GUARD_V1"
)

ACTION_MARKER = (
    "# ATTENDANCE_FUTURE_ACTION_GUARD_V1"
)


def replace_once(
    content: str,
    old: str,
    new: str,
    label: str,
) -> str:
    count = content.count(old)

    if count != 1:
        raise RuntimeError(
            f"{label}: expected 1 occurrence, "
            f"found {count}"
        )

    return content.replace(
        old,
        new,
        1,
    )


if not CHAT.exists():
    raise FileNotFoundError(CHAT)

if not ACTION.exists():
    raise FileNotFoundError(ACTION)


original_chat_bytes = CHAT.read_bytes()
original_action_bytes = ACTION.read_bytes()

original_chat = original_chat_bytes.decode(
    "utf-8-sig"
)

original_action = original_action_bytes.decode(
    "utf-8-sig"
)

chat_text = original_chat
action_text = original_action


if (
    CHAT_MARKER in chat_text
    and ACTION_MARKER in action_text
):
    print("ALREADY_PATCHED")
    raise SystemExit(0)


if (
    CHAT_MARKER in chat_text
    or ACTION_MARKER in action_text
):
    raise RuntimeError(
        "Partial attendance future patch detected."
    )


ACTION_HELPERS = r'''    # ATTENDANCE_FUTURE_ACTION_GUARD_V1
    @staticmethod
    def _attendance_ascii_digits(
        value: Any,
    ) -> str:
        return str(
            value
            or ""
        ).translate(
            str.maketrans(
                "۰۱۲۳۴۵۶۷۸۹",
                "0123456789",
            )
        ).strip()

    @classmethod
    def _attendance_date_key(
        cls,
        value: Any,
    ) -> tuple[
        int,
        int,
        int,
    ] | None:
        normalized = (
            cls._attendance_ascii_digits(
                value
            )
            .replace("-", "/")
            .replace(".", "/")
        )

        match = re.fullmatch(
            (
                r"\s*"
                r"([0-9]{4})"
                r"/"
                r"([0-9]{1,2})"
                r"/"
                r"([0-9]{1,2})"
                r"\s*"
            ),
            normalized,
        )

        if not match:
            return None

        year = int(
            match.group(1)
        )

        month = int(
            match.group(2)
        )

        day = int(
            match.group(3)
        )

        if not 1 <= month <= 12:
            return None

        if not 1 <= day <= 31:
            return None

        return (
            year,
            month,
            day,
        )

    @classmethod
    def _attendance_time_key(
        cls,
        value: Any,
    ) -> tuple[
        int,
        int,
    ] | None:
        normalized = (
            cls._attendance_ascii_digits(
                value
            )
        )

        match = re.fullmatch(
            (
                r"\s*"
                r"([0-9]{1,2})"
                r":"
                r"([0-9]{2})"
                r"(?:"
                r":"
                r"[0-9]{2}"
                r")?"
                r"\s*"
            ),
            normalized,
        )

        if not match:
            return None

        hour = int(
            match.group(1)
        )

        minute = int(
            match.group(2)
        )

        if not 0 <= hour <= 23:
            return None

        if not 0 <= minute <= 59:
            return None

        return (
            hour,
            minute,
        )

    def attendance_future_reason(
        self,
        event_date: Any,
        event_time: Any = None,
        *,
        today: Any = None,
        now_time: (
            str
            | tuple[int, int]
            | None
        ) = None,
    ) -> str | None:
        timezone_name = str(
            getattr(
                self.settings,
                "app_timezone",
                "Asia/Tehran",
            )
            or "Asia/Tehran"
        )

        today_value = (
            str(today)
            if today is not None
            else local_jalali_today(
                timezone_name
            )
        )

        event_date_key = (
            self._attendance_date_key(
                event_date
            )
        )

        today_key = (
            self._attendance_date_key(
                today_value
            )
        )

        if (
            event_date_key is None
            or today_key is None
        ):
            return None

        if event_date_key > today_key:
            return "future_date"

        if event_date_key < today_key:
            return None

        event_time_key = (
            self._attendance_time_key(
                event_time
            )
        )

        if event_time_key is None:
            return None

        if isinstance(
            now_time,
            tuple,
        ):
            current_time_key = (
                int(now_time[0]),
                int(now_time[1]),
            )

        elif now_time is not None:
            current_time_key = (
                self._attendance_time_key(
                    now_time
                )
            )

            if current_time_key is None:
                return None

        else:
            try:
                current = datetime.now(
                    ZoneInfo(
                        timezone_name
                    )
                )

            except Exception:
                current = (
                    datetime.now()
                    .astimezone()
                )

            current_time_key = (
                current.hour,
                current.minute,
            )

        if (
            event_time_key
            > current_time_key
        ):
            return "future_time"

        return None

    def _ensure_attendance_not_future(
        self,
        action_type: str,
        payload: dict[str, Any],
        *,
        today: Any = None,
        now_time: (
            str
            | tuple[int, int]
            | None
        ) = None,
    ) -> None:
        if action_type != "CREATE_TIME_EVENT":
            return

        reason = (
            self.attendance_future_reason(
                payload.get(
                    "eventDate"
                ),
                payload.get(
                    "eventTime"
                ),
                today=today,
                now_time=now_time,
            )
        )

        if reason is None:
            return

        raise AppError(
            (
                "ثبت تردد برای زمان آینده "
                "امکان‌پذیر نیست. لطفاً تاریخ "
                "و ساعت گذشته یا زمان فعلی "
                "را اعلام کنید."
            ),
            status_code=409,
            code=(
                "FUTURE_ATTENDANCE_NOT_ALLOWED"
            ),
            details={
                "reason": reason,
                "eventDate": payload.get(
                    "eventDate"
                ),
                "eventTime": payload.get(
                    "eventTime"
                ),
            },
        )

'''


CHAT_HELPER = r'''    # ATTENDANCE_FUTURE_CHAT_GUARD_V1
    async def _handle_future_attendance_guard(
        self,
        context: AgentContext,
        nlu_result: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not isinstance(
            nlu_result,
            dict,
        ):
            return None

        domain = str(
            nlu_result.get(
                "domain"
            )
            or ""
        )

        intent = str(
            nlu_result.get(
                "intent"
            )
            or ""
        )

        if domain != "ATTENDANCE":
            return None

        if intent not in {
            "CREATE_TIME_EVENT",
            "CREATE_TIME_EVENT_RANGE",
        }:
            return None

        entities = (
            nlu_result.get(
                "entities"
            )
            if isinstance(
                nlu_result.get(
                    "entities"
                ),
                dict,
            )
            else {}
        )

        event_date = (
            entities.get("date")
            or entities.get(
                "eventDate"
            )
        )

        event_time = (
            entities.get("time")
            or entities.get(
                "startTime"
            )
            or entities.get(
                "endTime"
            )
        )

        reason = (
            self.actions
            .attendance_future_reason(
                event_date,
                event_time,
                today=str(
                    context.date
                    or ""
                ),
            )
        )

        if reason is None:
            return None

        # No incomplete attendance conversation or
        # pending-action reference must survive.
        await self._delete_conversation_state(
            context
        )

        return {
            "reply": (
                "ثبت تردد برای زمان آینده "
                "امکان‌پذیر نیست. لطفاً تاریخ "
                "و ساعت گذشته یا زمان فعلی "
                "را اعلام کنید."
            ),
            "requiresConfirmation": False,
            "data": {
                "domain": "ATTENDANCE",
                "intent": intent,
                "blocked": True,
                "reasonCode": (
                    "FUTURE_ATTENDANCE_NOT_ALLOWED"
                ),
                "reason": reason,
                "eventDate": event_date,
                "eventTime": event_time,
            },
        }

'''


try:
    if not CHAT_BACKUP.exists():
        shutil.copy2(
            CHAT,
            CHAT_BACKUP,
        )

    if not ACTION_BACKUP.exists():
        shutil.copy2(
            ACTION,
            ACTION_BACKUP,
        )

    # ==============================================
    # ACTION SERVICE IMPORTS
    # ==============================================

    action_had_trailing_newline = (
        action_text.endswith("\n")
    )

    action_lines = (
        action_text.splitlines()
    )

    if not any(
        line.strip() == "import re"
        for line in action_lines
    ):
        logging_indexes = [
            index
            for index, line in enumerate(
                action_lines
            )
            if line.strip()
            == "import logging"
        ]

        if len(logging_indexes) != 1:
            raise RuntimeError(
                "import logging anchor: "
                f"found {len(logging_indexes)}"
            )

        action_lines.insert(
            logging_indexes[0] + 1,
            "import re",
        )

    if not any(
        line.strip()
        == "from zoneinfo import ZoneInfo"
        for line in action_lines
    ):
        datetime_indexes = [
            index
            for index, line in enumerate(
                action_lines
            )
            if line.strip()
            == (
                "from datetime import "
                "datetime, timedelta, timezone"
            )
        ]

        if len(datetime_indexes) != 1:
            raise RuntimeError(
                "datetime import anchor: "
                f"found {len(datetime_indexes)}"
            )

        action_lines.insert(
            datetime_indexes[0] + 1,
            "from zoneinfo import ZoneInfo",
        )

    if not any(
        line.strip()
        == (
            "from app.core.time "
            "import local_jalali_today"
        )
        for line in action_lines
    ):
        settings_indexes = [
            index
            for index, line in enumerate(
                action_lines
            )
            if line.strip()
            == (
                "from app.core.config "
                "import Settings"
            )
        ]

        if len(settings_indexes) != 1:
            raise RuntimeError(
                "Settings import anchor: "
                f"found {len(settings_indexes)}"
            )

        action_lines.insert(
            settings_indexes[0] + 1,
            (
                "from app.core.time "
                "import local_jalali_today"
            ),
        )

    action_text = "\n".join(
        action_lines
    )

    if action_had_trailing_newline:
        action_text += "\n"

    # ==============================================
    # ACTION SERVICE HELPERS
    # ==============================================

    action_text = replace_once(
        action_text,
        (
            "    def "
            "new_pending_action_record(\n"
        ),
        (
            ACTION_HELPERS
            + "    def "
            "new_pending_action_record(\n"
        ),
        "action helper anchor",
    )

    # Block future attendance before a Pending Action
    # is persisted.
    create_anchor = """        self._validate_payload(
            action_type,
            payload,
        )

        record = self.new_pending_action_record(
"""

    create_replacement = """        self._validate_payload(
            action_type,
            payload,
        )

        self._ensure_attendance_not_future(
            action_type,
            payload,
        )

        record = self.new_pending_action_record(
"""

    action_text = replace_once(
        action_text,
        create_anchor,
        create_replacement,
        "pending action future guard",
    )

    # Recheck during confirmation to protect old,
    # manually created or modified Pending Actions.
    execute_anchor = """    async def _execute(
        self,
        context: AgentContext,
        action_type: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
"""

    execute_replacement = execute_anchor + """        self._ensure_attendance_not_future(
            action_type,
            payload,
        )

"""

    action_text = replace_once(
        action_text,
        execute_anchor,
        execute_replacement,
        "execute future guard",
    )

    # ==============================================
    # CHAT SERVICE IMMEDIATE GUARD
    # ==============================================

    chat_had_trailing_newline = (
        chat_text.endswith("\n")
    )

    chat_lines = chat_text.splitlines()

    # ----------------------------------------------
    # 1. Insert future-attendance helper immediately
    #    before _handle_attendance.
    # ----------------------------------------------

    attendance_def_indexes = [
        index
        for index, line in enumerate(
            chat_lines
        )
        if line.strip()
        == "async def _handle_attendance("
    ]

    if len(attendance_def_indexes) != 1:
        raise RuntimeError(
            "_handle_attendance anchor: "
            f"found {len(attendance_def_indexes)}"
        )

    attendance_def_index = (
        attendance_def_indexes[0]
    )

    helper_lines = (
        CHAT_HELPER
        .rstrip("\n")
        .splitlines()
    )

    chat_lines[
        attendance_def_index:
        attendance_def_index
    ] = helper_lines

    # The insertion shifted all following indexes.
    attendance_def_index += len(
        helper_lines
    )

    # ----------------------------------------------
    # 2. Reject future attendance immediately after
    #    NLU and before pending-domain processing.
    # ----------------------------------------------

    domain_switch_indexes = [
        index
        for index, line in enumerate(
            chat_lines
        )
        if line.strip()
        == (
            "await self."
            "_cancel_pending_on_domain_switch("
        )
    ]

    if len(domain_switch_indexes) != 1:
        raise RuntimeError(
            "domain switch anchor: "
            f"found {len(domain_switch_indexes)}"
        )

    domain_switch_index = (
        domain_switch_indexes[0]
    )

    domain_indent = (
        chat_lines[domain_switch_index][
            :len(
                chat_lines[
                    domain_switch_index
                ]
            )
            - len(
                chat_lines[
                    domain_switch_index
                ].lstrip()
            )
        ]
    )

    domain_inner = domain_indent + "    "
    domain_nested = domain_inner + "    "

    immediate_guard_lines = [
        (
            domain_indent
            + "future_attendance_response = ("
        ),
        (
            domain_inner
            + "await self."
            + "_handle_future_attendance_guard("
        ),
        (
            domain_nested
            + "context,"
        ),
        (
            domain_nested
            + "nlu_result,"
        ),
        (
            domain_inner
            + ")"
        ),
        (
            domain_indent
            + ")"
        ),
        "",
        (
            domain_indent
            + "if future_attendance_response "
            + "is not None:"
        ),
        (
            domain_inner
            + "return "
            + "future_attendance_response"
        ),
        "",
    ]

    chat_lines[
        domain_switch_index:
        domain_switch_index
    ] = immediate_guard_lines

    # ----------------------------------------------
    # 3. Add a defensive check inside the legacy
    #    attendance handler.
    # ----------------------------------------------

    attendance_def_indexes = [
        index
        for index, line in enumerate(
            chat_lines
        )
        if line.strip()
        == "async def _handle_attendance("
    ]

    if len(attendance_def_indexes) != 1:
        raise RuntimeError(
            "_handle_attendance after insertion: "
            f"found {len(attendance_def_indexes)}"
        )

    attendance_def_index = (
        attendance_def_indexes[0]
    )

    is_create_indexes = [
        index
        for index in range(
            attendance_def_index,
            len(chat_lines),
        )
        if chat_lines[index].strip()
        == "is_create = ("
    ]

    if not is_create_indexes:
        raise RuntimeError(
            "is_create anchor was not found "
            "inside _handle_attendance"
        )

    is_create_index = (
        is_create_indexes[0]
    )

    not_create_index = next(
        (
            index
            for index in range(
                is_create_index + 1,
                min(
                    len(chat_lines),
                    is_create_index + 30,
                ),
            )
            if chat_lines[index].strip()
            == "if not is_create:"
        ),
        None,
    )

    if not_create_index is None:
        raise RuntimeError(
            "if not is_create anchor "
            "was not found"
        )

    handler_indent = (
        chat_lines[not_create_index][
            :len(
                chat_lines[
                    not_create_index
                ]
            )
            - len(
                chat_lines[
                    not_create_index
                ].lstrip()
            )
        ]
    )

    handler_inner = (
        handler_indent + "    "
    )

    handler_nested = (
        handler_inner + "    "
    )

    handler_deep = (
        handler_nested + "    "
    )

    handler_guard_lines = [
        (
            handler_indent
            + "if is_create:"
        ),
        (
            handler_inner
            + "handler_future_response = ("
        ),
        (
            handler_nested
            + "await self."
            + "_handle_future_attendance_guard("
        ),
        (
            handler_deep
            + "context,"
        ),
        (
            handler_deep
            + "{"
        ),
        (
            handler_deep
            + '    "domain": "ATTENDANCE",'
        ),
        (
            handler_deep
            + '    "intent": '
            + '"CREATE_TIME_EVENT",'
        ),
        (
            handler_deep
            + '    "entities": {'
        ),
        (
            handler_deep
            + '        "date": ('
        ),
        (
            handler_deep
            + "            target_dates[0]"
        ),
        (
            handler_deep
            + "            if target_dates"
        ),
        (
            handler_deep
            + "            else None"
        ),
        (
            handler_deep
            + "        ),"
        ),
        (
            handler_deep
            + '        "time": ('
        ),
        (
            handler_deep
            + "            times[0]"
        ),
        (
            handler_deep
            + "            if times"
        ),
        (
            handler_deep
            + "            else None"
        ),
        (
            handler_deep
            + "        ),"
        ),
        (
            handler_deep
            + "    },"
        ),
        (
            handler_deep
            + "},"
        ),
        (
            handler_nested
            + ")"
        ),
        (
            handler_inner
            + ")"
        ),
        "",
        (
            handler_inner
            + "if handler_future_response "
            + "is not None:"
        ),
        (
            handler_nested
            + "return "
            + "handler_future_response"
        ),
        "",
    ]

    chat_lines[
        not_create_index:
        not_create_index
    ] = handler_guard_lines

    chat_text = "\n".join(
        chat_lines
    )

    if chat_had_trailing_newline:
        chat_text += "\n"

    # ==============================================
    # WRITE AND COMPILE
    # ==============================================
    # ==============================================

    CHAT.write_text(
        chat_text,
        encoding="utf-8",
    )

    ACTION.write_text(
        action_text,
        encoding="utf-8",
    )

    py_compile.compile(
        str(CHAT),
        doraise=True,
    )

    py_compile.compile(
        str(ACTION),
        doraise=True,
    )

    # ==============================================
    # RUNTIME TESTS
    # ==============================================

    sys.path.insert(
        0,
        str(ROOT),
    )

    for module_name in (
        "app.application.services.chat_service",
        "app.application.services.action_service",
    ):
        sys.modules.pop(
            module_name,
            None,
        )

    importlib.invalidate_caches()

    action_module = importlib.import_module(
        "app.application.services.action_service"
    )

    chat_module = importlib.import_module(
        "app.application.services.chat_service"
    )

    exceptions_module = importlib.import_module(
        "app.core.exceptions"
    )

    ActionService = (
        action_module.ActionService
    )

    ChatService = (
        chat_module.ChatService
    )

    AppError = (
        exceptions_module.AppError
    )

    action = object.__new__(
        ActionService
    )

    action.settings = SimpleNamespace(
        app_timezone="Asia/Tehran",
    )

    # Future date is rejected even without a time.
    if (
        action.attendance_future_reason(
            "1405/05/03",
            None,
            today="1405/05/02",
            now_time="10:00",
        )
        != "future_date"
    ):
        raise RuntimeError(
            "Future-date detection failed"
        )

    # Future time for today is rejected.
    if (
        action.attendance_future_reason(
            "1405/05/02",
            "11:00",
            today="1405/05/02",
            now_time="10:00",
        )
        != "future_time"
    ):
        raise RuntimeError(
            "Future-time detection failed"
        )

    # Current and past times are accepted.
    for allowed_time in (
        "09:59",
        "10:00",
    ):
        if (
            action.attendance_future_reason(
                "1405/05/02",
                allowed_time,
                today="1405/05/02",
                now_time="10:00",
            )
            is not None
        ):
            raise RuntimeError(
                "Allowed attendance time "
                f"was blocked: {allowed_time}"
            )

    # Past dates are accepted.
    if (
        action.attendance_future_reason(
            "1405/05/01",
            "23:59",
            today="1405/05/02",
            now_time="10:00",
        )
        is not None
    ):
        raise RuntimeError(
            "Past attendance date was blocked"
        )

    # Pending Action validation must reject future data.
    try:
        action._ensure_attendance_not_future(
            "CREATE_TIME_EVENT",
            {
                "eventDate": "1405/05/03",
                "eventTime": "08:00",
            },
            today="1405/05/02",
            now_time="10:00",
        )

    except AppError as exc:
        if (
            getattr(
                exc,
                "code",
                "",
            )
            != "FUTURE_ATTENDANCE_NOT_ALLOWED"
        ):
            raise

    else:
        raise RuntimeError(
            "Future Pending Action was accepted"
        )

    class FakeActions:
        def attendance_future_reason(
            self,
            event_date,
            event_time=None,
            *,
            today=None,
            now_time=None,
        ):
            if (
                str(event_date)
                == "1405/05/03"
            ):
                return "future_date"

            return None

    async def run_chat_tests() -> None:
        chat = object.__new__(
            ChatService
        )

        chat.actions = FakeActions()

        deleted = []

        async def fake_delete(
            context,
        ):
            deleted.append(True)

        chat._delete_conversation_state = (
            fake_delete
        )

        context = SimpleNamespace(
            date="1405/05/02",
        )

        blocked = (
            await chat
            ._handle_future_attendance_guard(
                context,
                {
                    "domain": "ATTENDANCE",
                    "intent": (
                        "CREATE_TIME_EVENT"
                    ),
                    "entities": {
                        "date": "1405/05/03",
                    },
                },
            )
        )

        if blocked is None:
            raise RuntimeError(
                "Chat did not block future date"
            )

        if blocked.get(
            "requiresConfirmation"
        ):
            raise RuntimeError(
                "Future attendance requested "
                "confirmation"
            )

        if blocked.get(
            "pendingAction"
        ):
            raise RuntimeError(
                "Future attendance created "
                "a Pending Action"
            )

        if not deleted:
            raise RuntimeError(
                "Future attendance state "
                "was not cleared"
            )

        allowed = (
            await chat
            ._handle_future_attendance_guard(
                context,
                {
                    "domain": "ATTENDANCE",
                    "intent": (
                        "CREATE_TIME_EVENT"
                    ),
                    "entities": {
                        "date": "1405/05/01",
                        "time": "08:00",
                    },
                },
            )
        )

        if allowed is not None:
            raise RuntimeError(
                "Past attendance was blocked"
            )

    asyncio.run(
        run_chat_tests()
    )

    if CHAT_MARKER not in chat_text:
        raise RuntimeError(
            "Chat marker missing"
        )

    if ACTION_MARKER not in action_text:
        raise RuntimeError(
            "Action marker missing"
        )

    print("PATCH_OK")
    print(
        "ATTENDANCE_FUTURE_GUARD_TESTS_OK"
    )
    print(
        f"CHAT_BACKUP={CHAT_BACKUP}"
    )
    print(
        f"ACTION_BACKUP={ACTION_BACKUP}"
    )

except Exception:
    CHAT.write_bytes(
        original_chat_bytes
    )

    ACTION.write_bytes(
        original_action_bytes
    )

    print(
        "PATCH_FAILED_ROLLED_BACK"
    )

    traceback.print_exc()
    raise