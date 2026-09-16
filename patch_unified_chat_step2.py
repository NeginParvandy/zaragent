from __future__ import annotations

from pathlib import Path
import shutil


TARGET = Path(
    r"D:\serviceAi\app\application\services\chat_service.py"
)

REPOSITORY = Path(
    r"D:\serviceAi\app\infrastructure\repositories"
    r"\state_repository.py"
)

BACKUP = Path(
    r"D:\serviceAi\app\application\services"
    r"\chat_service.py.bak_before_unified_chat_step2"
)

METHOD_MARKER = (
    "    async def _handle_pending_action_reply("
)

HANDLE_ANCHOR = '''        pending_state_response = await self._handle_pending_chat_state(
            context,
            text,
        )
        if pending_state_response is not None:
            return pending_state_response

        try:
'''

HANDLE_REPLACEMENT = '''        pending_state_response = await self._handle_pending_chat_state(
            context,
            text,
        )
        if pending_state_response is not None:
            return pending_state_response

        pending_action_response = (
            await self._handle_pending_action_reply(
                context,
                text,
            )
        )
        if pending_action_response is not None:
            return pending_action_response

        try:
'''

METHOD_ANCHOR = '''    async def _handle_pending_chat_state(
'''

NEW_METHODS = '''    async def _handle_pending_action_reply(
        self,
        context: AgentContext,
        text: str,
    ) -> dict[str, Any] | None:
        reply_kind = (
            self._pending_action_reply_kind(text)
        )

        if reply_kind is None:
            return None

        employee_id = str(
            context.employee_id or ""
        ).strip()

        if not employee_id:
            raise AppError(
                "کد پرسنلی کاربر مشخص نیست.",
                code="MISSING_EMPLOYEE_ID",
            )

        pending_action = await asyncio.to_thread(
            self.repository.get_latest_pending_action,
            employee_id,
        )

        if pending_action is None:
            return {
                "reply": (
                    "در حال حاضر عملیاتی در انتظار "
                    "تأیید یا لغو ندارید."
                ),
                "requiresConfirmation": False,
                "data": {
                    "pendingAction": None,
                },
            }

        if reply_kind == "confirm":
            result = await self.actions.confirm(
                context,
                pending_action.id,
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

        result = await self.actions.cancel(
            context,
            pending_action.id,
        )

        current_status = result.get(
            "currentStatus"
        )

        if not current_status:
            current_status = (
                "cancelled"
                if result.get("cancelled")
                else "not_cancelled"
            )

        return {
            "reply": (
                result.get("message")
                or "عملیات لغو شد."
            ),
            "requiresConfirmation": False,
            "action": {
                "id": pending_action.id,
                "type": (
                    pending_action.action_type
                ),
                "status": current_status,
            },
            "data": result,
        }

    @staticmethod
    def _pending_action_reply_kind(
        text: str,
    ) -> str | None:
        normalized = normalize_persian_text(
            text
        )

        normalized = re.sub(
            r"[،,؛;.!؟?]+",
            " ",
            normalized,
        )

        normalized = re.sub(
            r"\\s+",
            " ",
            normalized,
        ).strip()

        confirm_phrases = {
            "بله",
            "اره",
            "آره",
            "اوکی",
            "باشه",
            "تایید",
            "تأیید",
            "تایید میکنم",
            "تأیید میکنم",
            "تایید می کنم",
            "تأیید می کنم",
            "انجام بده",
            "ادامه بده",
            "بله انجام بده",
            "بله تایید میکنم",
            "بله تأیید میکنم",
            "بله لطفا",
            "بله لطفاً",
            "yes",
            "ok",
            "confirm",
        }

        cancel_phrases = {
            "نه",
            "خیر",
            "لغو",
            "لغو کن",
            "بیخیال",
            "بی خیال",
            "انصراف",
            "نمیخوام",
            "نمی خواهم",
            "نمیخوامش",
            "no",
            "cancel",
        }

        if normalized in confirm_phrases:
            return "confirm"

        if normalized in cancel_phrases:
            return "cancel"

        return None

    @staticmethod
    def _action_success_reply(
        action_type: str,
    ) -> str:
        messages = {
            "RESERVE_FOOD": (
                "رزرو غذا با موفقیت انجام شد."
            ),
            "CANCEL_FOOD": (
                "رزرو غذا با موفقیت لغو شد."
            ),
            "RATE_FOOD": (
                "امتیاز غذا با موفقیت ثبت شد."
            ),
            "CREATE_LEAVE": (
                "درخواست با موفقیت ثبت شد."
            ),
            "DELETE_LEAVE": (
                "درخواست با موفقیت حذف شد."
            ),
            "CREATE_TIME_EVENT": (
                "تردد با موفقیت ثبت شد."
            ),
        }

        return messages.get(
            action_type,
            "عملیات با موفقیت انجام شد.",
        )

'''

if not TARGET.exists():
    raise FileNotFoundError(
        f"Target file was not found: {TARGET}"
    )

if not REPOSITORY.exists():
    raise FileNotFoundError(
        f"Repository file was not found: {REPOSITORY}"
    )

repository_text = REPOSITORY.read_text(
    encoding="utf-8-sig"
)

if "def get_latest_pending_action(" not in repository_text:
    raise RuntimeError(
        "Repository step 1 is missing. "
        "No file was changed."
    )

original_text = TARGET.read_text(
    encoding="utf-8-sig"
)

if METHOD_MARKER in original_text:
    print(
        "No change was needed: unified chat "
        "action handling already exists."
    )
    raise SystemExit(0)

if HANDLE_ANCHOR not in original_text:
    raise RuntimeError(
        "Chat handle anchor was not found. "
        "No file was changed."
    )

if METHOD_ANCHOR not in original_text:
    raise RuntimeError(
        "Method insertion anchor was not found. "
        "No file was changed."
    )

patched_text = original_text.replace(
    HANDLE_ANCHOR,
    HANDLE_REPLACEMENT,
    1,
)

patched_text = patched_text.replace(
    METHOD_ANCHOR,
    NEW_METHODS + METHOD_ANCHOR,
    1,
)

compile(
    patched_text,
    str(TARGET),
    "exec",
)

if not BACKUP.exists():
    shutil.copy2(
        TARGET,
        BACKUP,
    )

TARGET.write_text(
    patched_text,
    encoding="utf-8",
    newline="\n",
)

print(
    "SUCCESS: unified chat confirmation "
    "and cancellation were added safely."
)
print(
    f"Backup: {BACKUP}"
)