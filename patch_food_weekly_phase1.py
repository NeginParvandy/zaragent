from __future__ import annotations

import py_compile
import sys
from pathlib import Path
from shutil import copy2


TARGET_FILE = Path(
    r"D:\serviceAi\app\application\services\food_service.py"
)

BACKUP_FILE = Path(
    r"D:\serviceAi\app\application\services"
    r"\food_service.py.bak_before_weekly_phase1"
)

MARKER = "# WEEKLY_FOOD_INSPECTION_PHASE1"


def fail(message: str) -> None:
    print(f"FAILED: {message}")
    sys.exit(1)


def main() -> None:
    if not TARGET_FILE.exists():
        fail(f"Target file not found: {TARGET_FILE}")

    original_text = TARGET_FILE.read_text(
        encoding="utf-8"
    )

    if MARKER in original_text:
        print(
            "SKIPPED: Weekly food inspection "
            "phase 1 is already installed."
        )
        return

    updated_text = original_text

    import_anchor = (
        "import asyncio\n"
        "import logging\n"
    )

    if import_anchor not in updated_text:
        fail("Import anchor was not found.")

    updated_text = updated_text.replace(
        import_anchor,
        (
            "import asyncio\n"
            "import json\n"
            "import logging\n"
        ),
        1,
    )

    collections_anchor = (
        "from collections import Counter\n"
        "from typing import Any\n"
    )

    if collections_anchor not in updated_text:
        fail("Collections import anchor was not found.")

    updated_text = updated_text.replace(
        collections_anchor,
        (
            "from collections import Counter\n"
            "from pathlib import Path\n"
            "from typing import Any\n"
        ),
        1,
    )

    logger_anchor = (
        "logger = logging.getLogger(__name__)\n"
    )

    if logger_anchor not in updated_text:
        fail("Logger anchor was not found.")

    inspection_helpers = '''
logger = logging.getLogger(__name__)

# WEEKLY_FOOD_INSPECTION_PHASE1
WEEKLY_FOOD_INSPECTION_FILE = Path(
    r"D:\\serviceAi\\food_weekly_inspection.json"
)


def _is_sensitive_inspection_key(key: object) -> bool:
    normalized = "".join(
        character
        for character in str(key).lower()
        if character.isalnum()
    )

    sensitive_parts = (
        "authorization",
        "token",
        "password",
        "usernamehash",
        "passwordhash",
        "digitcode",
        "session",
        "secret",
        "cookie",
        "apikey",
    )

    return any(
        part in normalized
        for part in sensitive_parts
    )


def _sanitize_inspection_value(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}

        for key, item in value.items():
            if _is_sensitive_inspection_key(key):
                continue

            sanitized[str(key)] = (
                _sanitize_inspection_value(item)
            )

        return sanitized

    if isinstance(value, list):
        return [
            _sanitize_inspection_value(item)
            for item in value
        ]

    if isinstance(value, tuple):
        return [
            _sanitize_inspection_value(item)
            for item in value
        ]

    return value


def _mask_employee_id(
    employee_id: str | None,
) -> str:
    value = str(employee_id or "").strip()

    if not value:
        return ""

    if len(value) <= 4:
        return "*" * len(value)

    return (
        "*" * (len(value) - 4)
        + value[-4:]
    )
'''

    updated_text = updated_text.replace(
        logger_anchor,
        inspection_helpers,
        1,
    )

    recommend_anchor = '''        menu, history = await asyncio.gather(self.get_weekly_menu(context), self._safe_history(context))
        favorite_names = self._favorite_food_names(history)
'''

    if recommend_anchor not in updated_text:
        fail(
            "recommend_food anchor was not found."
        )

    recommend_replacement = '''        menu, history = await asyncio.gather(
            self.get_weekly_menu(context),
            self._safe_history(context),
        )

        await self._write_weekly_inspection(
            context=context,
            menu=menu,
            history=history,
        )

        favorite_names = self._favorite_food_names(history)
'''

    updated_text = updated_text.replace(
        recommend_anchor,
        recommend_replacement,
        1,
    )

    safe_history_anchor = '''    async def _safe_history(self, context: AgentContext) -> list[dict[str, Any]]:
        try:
            return await self.get_history(context)
        except Exception as exc:
            logger.warning("Food history lookup failed error=%s", type(exc).__name__)
            return []
'''

    if safe_history_anchor not in updated_text:
        fail("_safe_history anchor was not found.")

    inspection_method = safe_history_anchor + '''

    async def _write_weekly_inspection(
        self,
        *,
        context: AgentContext,
        menu: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> None:
        try:
            inspection_payload = {
                "employeeIdMasked": _mask_employee_id(
                    context.employee_id
                ),
                "restaurantId": context.restaurant_id,
                "mealId": context.meal_id,
                "menu": menu,
                "history": history,
            }

            sanitized_payload = (
                _sanitize_inspection_value(
                    inspection_payload
                )
            )

            output_text = json.dumps(
                sanitized_payload,
                ensure_ascii=False,
                indent=2,
                default=str,
            )

            await asyncio.to_thread(
                WEEKLY_FOOD_INSPECTION_FILE.write_text,
                output_text,
                encoding="utf-8",
            )

            logger.info(
                "Weekly food inspection saved path=%s",
                WEEKLY_FOOD_INSPECTION_FILE,
            )

        except Exception as exc:
            logger.warning(
                "Weekly food inspection failed "
                "error=%s",
                type(exc).__name__,
            )
'''

    updated_text = updated_text.replace(
        safe_history_anchor,
        inspection_method,
        1,
    )

    copy2(
        TARGET_FILE,
        BACKUP_FILE,
    )

    try:
        TARGET_FILE.write_text(
            updated_text,
            encoding="utf-8",
        )

        py_compile.compile(
            str(TARGET_FILE),
            doraise=True,
        )

    except Exception as exc:
        copy2(
            BACKUP_FILE,
            TARGET_FILE,
        )

        fail(
            "Patch was rolled back because "
            f"validation failed: {exc}"
        )

    print("SUCCESS")
    print(f"Patched: {TARGET_FILE}")
    print(f"Backup: {BACKUP_FILE}")
    print(
        "Inspection output will be saved to: "
        r"D:\serviceAi\food_weekly_inspection.json"
    )


if __name__ == "__main__":
    main()