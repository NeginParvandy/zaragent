# -*- coding: utf-8 -*-

from __future__ import annotations

import py_compile
import shutil
import sys
from pathlib import Path


ROOT = Path(r"D:\serviceAi")

CHAT = (
    ROOT
    / "app"
    / "application"
    / "services"
    / "chat_service.py"
)

GUARD = (
    ROOT
    / "app"
    / "application"
    / "services"
    / "intent_guard.py"
)

CHAT_BACKUP = CHAT.with_name(
    "chat_service.py.bak_before_food_final_part1"
)

GUARD_BACKUP = GUARD.with_name(
    "intent_guard.py.bak_before_food_final_part1"
)

CHAT_MARKER = "# FOOD_FINAL_PART1_ORDER_V1"
GUARD_MARKER = "# FOOD_FINAL_PART1_GUARD_V1"


def require_once(
    content: str,
    needle: str,
    label: str,
) -> None:
    count = content.count(needle)

    if count != 1:
        raise RuntimeError(
            f"{label}: expected 1 occurrence, found {count}"
        )


def insert_before_closing_set(
    content: str,
    anchor_item: str,
    new_items: str,
    label: str,
) -> str:
    anchor = (
        f'        "{anchor_item}",\n'
        "    }"
    )

    require_once(
        content,
        anchor,
        label,
    )

    replacement = (
        f'        "{anchor_item}",\n'
        f"{new_items}"
        "    }"
    )

    return content.replace(
        anchor,
        replacement,
        1,
    )


if not CHAT.exists():
    raise FileNotFoundError(CHAT)

if not GUARD.exists():
    raise FileNotFoundError(GUARD)


original_chat = CHAT.read_text(
    encoding="utf-8-sig"
)

original_guard = GUARD.read_text(
    encoding="utf-8-sig"
)

chat_text = original_chat
guard_text = original_guard


try:
    if not CHAT_BACKUP.exists():
        shutil.copy2(
            CHAT,
            CHAT_BACKUP,
        )

    if not GUARD_BACKUP.exists():
        shutil.copy2(
            GUARD,
            GUARD_BACKUP,
        )

    # -------------------------------------------------
    # 1. Move IntentGuard after pending state/actions.
    # -------------------------------------------------

    if CHAT_MARKER not in chat_text:
        old_guard_block = """        intent_decision = self.intent_guard.analyze(
            text
        )

        if not intent_decision.allowed:
            return intent_decision.to_response()

"""

        require_once(
            chat_text,
            old_guard_block,
            "chat guard block",
        )

        chat_text = chat_text.replace(
            old_guard_block,
            "",
            1,
        )

        control_anchor = """        if control_response is not None:
            return control_response

        if self._is_help(text):
"""

        require_once(
            chat_text,
            control_anchor,
            "chat control anchor",
        )

        control_replacement = f"""        if control_response is not None:
            return control_response

        {CHAT_MARKER}
        intent_decision = self.intent_guard.analyze(
            text
        )

        if not intent_decision.allowed:
            return intent_decision.to_response()

        if self._is_help(text):
"""

        chat_text = chat_text.replace(
            control_anchor,
            control_replacement,
            1,
        )

    # -------------------------------------------------
    # 2. Expand Guard vocabulary and defer ambiguous
    #    organizational commands to NLU/Router.
    # -------------------------------------------------

    if GUARD_MARKER not in guard_text:
        class_anchor = "    CONTROL_REPLIES = {\n"

        require_once(
            guard_text,
            class_anchor,
            "guard class anchor",
        )

        guard_text = guard_text.replace(
            class_anchor,
            (
                f"    {GUARD_MARKER}\n"
                + class_anchor
            ),
            1,
        )

        guard_text = insert_before_closing_set(
            guard_text,
            "بی خیال",
            """        "بله لطفا",
        "بله لطفاً",
        "بله انجام بده",
        "بله تایید میکنم",
        "بله تأیید میکنم",
        "تایید میکنم",
        "تأیید میکنم",
        "تایید می کنم",
        "تأیید می کنم",
        "لغو کن",
        "کنسل کن",
        "حذف کن",
        "نمیخوام",
        "نمی خواهم",
        "yes",
        "ok",
        "confirm",
        "cancel",
""",
            "CONTROL_REPLIES",
        )

        guard_text = insert_before_closing_set(
            guard_text,
            "چی دارم",
            """        "نشون بده",
        "نشون",
        "چیه",
        "چی هست",
        "چی داریم",
        "چه غذایی",
        "بده",
        "بیار",
""",
            "READ_TERMS",
        )

        guard_text = insert_before_closing_set(
            guard_text,
            "سفارش بده",
            """        "ثبت کن",
        "ثبت شه",
        "ثبت شود",
        "ثبتش کن",
        "رزرو شه",
        "رزرو شود",
        "انتخاب کن",
        "انتخاب شه",
        "انتخاب شود",
        "انتخابش کن",
        "بگیرش",
""",
            "CREATE_TERMS",
        )

        guard_text = insert_before_closing_set(
            guard_text,
            "تاریخ",
            """        "شنبه",
        "یکشنبه",
        "یک شنبه",
        "دوشنبه",
        "دو شنبه",
        "سه شنبه",
        "سهشنبه",
        "چهارشنبه",
        "چهار شنبه",
        "پنجشنبه",
        "پنج شنبه",
        "جمعه",
""",
            "TIME_HINTS",
        )

        guard_text = insert_before_closing_set(
            guard_text,
            "بررسی کن",
            """        "ثبت شه",
        "ثبت شود",
        "ثبتش کن",
        "رزرو کن",
        "رزرو شه",
        "رزرو شود",
        "انتخاب کن",
        "انتخاب شه",
        "انتخاب شود",
        "انتخابش کن",
        "برام بگیر",
        "برایم بگیر",
        "سفارش بده",
        "نشون بده",
""",
            "AMBIGUOUS_ACTION_TERMS",
        )

        ambiguous_start = guard_text.find(
            "            if has_ambiguous_action:\n"
        )

        if ambiguous_start < 0:
            raise RuntimeError(
                "ambiguous action block start not found"
            )

        next_return = guard_text.find(
            "\n\n            return IntentDecision(",
            ambiguous_start,
        )

        if next_return < 0:
            raise RuntimeError(
                "ambiguous action block end not found"
            )

        deferred_block = """            if has_ambiguous_action:
                return IntentDecision(
                    allowed=True,
                    status="DEFERRED",
                    domain="UNKNOWN",
                    intent="DEFER_TO_NLU",
                    confidence=0.70,
                )"""

        guard_text = (
            guard_text[:ambiguous_start]
            + deferred_block
            + guard_text[next_return:]
        )

    CHAT.write_text(
        chat_text,
        encoding="utf-8",
    )

    GUARD.write_text(
        guard_text,
        encoding="utf-8",
    )

    # -------------------------------------------------
    # 3. Syntax tests.
    # -------------------------------------------------

    py_compile.compile(
        str(CHAT),
        doraise=True,
    )

    py_compile.compile(
        str(GUARD),
        doraise=True,
    )

    # -------------------------------------------------
    # 4. Verify execution order inside handle().
    # -------------------------------------------------

    handle_start = chat_text.find(
        "    async def handle("
    )

    handle_end = chat_text.find(
        "\n    def ",
        handle_start,
    )

    if handle_end < 0:
        handle_end = chat_text.find(
            "\n    async def ",
            handle_start + 10,
        )

    handle_block = chat_text[
        handle_start:handle_end
    ]

    order_points = [
        handle_block.find(
            "pending_state_response"
        ),
        handle_block.find(
            "conversation_payload ="
        ),
        handle_block.find(
            "control_response ="
        ),
        handle_block.find(
            CHAT_MARKER
        ),
        handle_block.find(
            "if self._is_help(text):"
        ),
    ]

    if any(
        position < 0
        for position in order_points
    ):
        raise RuntimeError(
            f"handle order point missing: {order_points}"
        )

    if order_points != sorted(order_points):
        raise RuntimeError(
            f"handle order is incorrect: {order_points}"
        )

    # -------------------------------------------------
    # 5. Runtime tests for IntentGuard.
    # -------------------------------------------------

    sys.path.insert(
        0,
        str(ROOT),
    )

    from app.application.services.intent_guard import (
        IntentGuard,
    )

    guard = IntentGuard()

    allowed_cases = [
        "غذای فردا چیه",
        "غذای امروز چیه",
        "غذای یکشنبه 4 مرداد رو نشون بده",
        "برای سه شنبه واویشکا رزرو کن",
        "برای یکشنبه قیمه سیب زمینی رو ثبت کن",
        "پلو یونانی ثبت شه",
        "بله لطفاً",
        "لغو کن",
    ]

    for message in allowed_cases:
        decision = guard.analyze(
            message
        )

        if not decision.allowed:
            raise RuntimeError(
                "Guard incorrectly blocked: "
                f"{message!r} -> "
                f"{decision.status}/"
                f"{decision.intent}"
            )

    blocked_cases = [
        "قیمت دلار چنده",
        "نتیجه بازی فوتبال چیه",
        "طرز تهیه قورمه سبزی",
    ]

    for message in blocked_cases:
        decision = guard.analyze(
            message
        )

        if decision.allowed:
            raise RuntimeError(
                "Guard incorrectly allowed: "
                f"{message!r} -> "
                f"{decision.status}/"
                f"{decision.intent}"
            )

    print("PATCH_OK")
    print("PART1_TESTS_OK")
    print(f"CHAT_BACKUP={CHAT_BACKUP}")
    print(f"GUARD_BACKUP={GUARD_BACKUP}")

except Exception:
    CHAT.write_text(
        original_chat,
        encoding="utf-8",
    )

    GUARD.write_text(
        original_guard,
        encoding="utf-8",
    )

    print("PATCH_FAILED_ROLLED_BACK")
    raise