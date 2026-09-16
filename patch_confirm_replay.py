from pathlib import Path
import shutil


TARGET = Path(
    r"D:\serviceAi\app\application\services\chat_service.py"
)
BACKUP = Path(
    r"D:\serviceAi\app\application\services"
    r"\chat_service.py.bak_before_confirm_replay"
)
TEMP = Path(
    r"D:\serviceAi\app\application\services"
    r"\chat_service.py.confirm_replay.tmp"
)

MARKER = "CONFIRM_REPLAY_CACHE_V1"


text = TARGET.read_text(encoding="utf-8-sig")

if MARKER in text:
    print("ALREADY_PATCHED")
    raise SystemExit(0)


def replace_once(
    old: str,
    new: str,
    label: str,
) -> None:
    global text

    count = text.count(old)

    if count != 1:
        raise RuntimeError(
            f"{label}: expected 1 match, found {count}"
        )

    text = text.replace(old, new, 1)


replace_once(
    """import asyncio
import re
from typing import Any
""",
    """import asyncio
import re
import time
from typing import Any
""",
    "IMPORT_TIME",
)


replace_once(
    """CONVERSATION_STATE = "conversation"
CONVERSATION_STATE_TTL_MINUTES = 30
FOOD_MEAL_ID = 1
""",
    """CONVERSATION_STATE = "conversation"
CONVERSATION_STATE_TTL_MINUTES = 30

# CONFIRM_REPLAY_CACHE_V1
CONFIRM_REPLAY_TTL_SECONDS = 20
CONFIRM_REPLAY_WAIT_SECONDS = 5

FOOD_MEAL_ID = 1
""",
    "REPLAY_CONSTANTS",
)


helper_code = '''    def _confirmation_replay_response(
        self,
        conversation_payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        cached = conversation_payload.get(
            "lastSuccessfulAction"
        )

        if not isinstance(cached, dict):
            return None

        try:
            completed_at = float(
                cached.get("completedAtEpoch")
            )
        except (TypeError, ValueError):
            return None

        age_seconds = time.time() - completed_at

        if (
            age_seconds < 0
            or age_seconds
            > CONFIRM_REPLAY_TTL_SECONDS
        ):
            return None

        action_id = str(
            cached.get("actionId") or ""
        ).strip()

        action_type = str(
            cached.get("actionType") or ""
        ).strip()

        if not action_id or not action_type:
            return None

        status = str(
            cached.get("status") or "succeeded"
        ).strip()

        reply = str(
            cached.get("reply")
            or self._action_success_reply(
                action_type
            )
        )

        return {
            "reply": reply,
            "requiresConfirmation": False,
            "action": {
                "id": action_id,
                "type": action_type,
                "status": status,
            },
            "data": cached.get("data"),
        }

    async def _wait_for_confirmation_replay(
        self,
        context: AgentContext,
    ) -> dict[str, Any] | None:
        interval_seconds = 0.2
        attempts = max(
            1,
            int(
                CONFIRM_REPLAY_WAIT_SECONDS
                / interval_seconds
            ),
        )

        for attempt in range(attempts):
            current_payload = (
                await self._load_conversation_payload(
                    context
                )
            )

            replay_response = (
                self._confirmation_replay_response(
                    current_payload
                )
            )

            if replay_response is not None:
                return replay_response

            if attempt + 1 < attempts:
                await asyncio.sleep(
                    interval_seconds
                )

        return None

'''


replace_once(
    """    async def _handle_pending_action_reply(
""",
    helper_code
    + """    async def _handle_pending_action_reply(
""",
    "REPLAY_HELPERS",
)


old_confirm_block = '''        if reply_kind == "confirm":
            if pending_action is None:
                return {
                    "reply": (
                        "در این مکالمه عملیاتی "
                        "در انتظار تأیید نیست."
                    ),
                    "requiresConfirmation": False,
                    "data": {
                        "pendingAction": None,
                    },
                }

            result = await self.actions.confirm(
                context,
                pending_action.id,
            )

            await self._delete_conversation_state(
                context
            )

            return {
                "reply": self._action_success_reply(
                    pending_action.action_type
                ),
                "requiresConfirmation": False,
                "action": {
                    "id": pending_action.id,
                    "type": (
                        pending_action.action_type
                    ),
                    "status": (
                        result.get("status")
                        or "succeeded"
                    ),
                },
                "data": result.get(
                    "result",
                    result,
                ),
            }
'''


new_confirm_block = '''        if reply_kind == "confirm":
            if pending_action is None:
                replay_response = (
                    self._confirmation_replay_response(
                        conversation_payload
                    )
                )

                if (
                    replay_response is None
                    and pending_action_id
                ):
                    replay_response = (
                        await self
                        ._wait_for_confirmation_replay(
                            context
                        )
                    )

                if replay_response is not None:
                    return replay_response

                return {
                    "reply": (
                        "در این مکالمه عملیاتی "
                        "در انتظار تأیید نیست."
                    ),
                    "requiresConfirmation": False,
                    "data": {
                        "pendingAction": None,
                    },
                }

            try:
                result = await self.actions.confirm(
                    context,
                    pending_action.id,
                )
            except AppError as exc:
                details = (
                    getattr(exc, "details", None)
                    or {}
                )

                current_status = str(
                    details.get("status") or ""
                ).strip()

                if (
                    getattr(
                        exc,
                        "status_code",
                        None,
                    )
                    == 409
                    and current_status
                    in {
                        "processing",
                        "succeeded",
                    }
                ):
                    replay_response = (
                        await self
                        ._wait_for_confirmation_replay(
                            context
                        )
                    )

                    if replay_response is not None:
                        return replay_response

                raise

            success_reply = (
                self._action_success_reply(
                    pending_action.action_type
                )
            )

            success_status = str(
                result.get("status")
                or "succeeded"
            )

            success_data = result.get(
                "result",
                result,
            )

            await self._save_conversation_payload(
                context,
                {
                    "lastSuccessfulAction": {
                        "actionId": (
                            pending_action.id
                        ),
                        "actionType": (
                            pending_action.action_type
                        ),
                        "status": success_status,
                        "reply": success_reply,
                        "data": success_data,
                        "completedAtEpoch": (
                            time.time()
                        ),
                    },
                },
            )

            return {
                "reply": success_reply,
                "requiresConfirmation": False,
                "action": {
                    "id": pending_action.id,
                    "type": (
                        pending_action.action_type
                    ),
                    "status": success_status,
                },
                "data": success_data,
            }
'''


replace_once(
    old_confirm_block,
    new_confirm_block,
    "CONFIRM_HANDLER",
)


replace_once(
    '''            "CREATE_LEAVE": (
                "درخواست با موفقیت ثبت شد."
            ),
''',
    '''            "CREATE_LEAVE": (
                "✅ درخواست مرخصی با موفقیت ثبت شد."
            ),
''',
    "LEAVE_SUCCESS_MESSAGE",
)


compile(
    text,
    str(TARGET),
    "exec",
)

if not BACKUP.exists():
    shutil.copy2(
        TARGET,
        BACKUP,
    )

TEMP.write_text(
    text,
    encoding="utf-8",
)

TEMP.replace(TARGET)

print("PATCH_OK")
print(f"BACKUP={BACKUP}")