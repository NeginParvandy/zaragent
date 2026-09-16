# -*- coding: utf-8 -*-

from pathlib import Path
import py_compile
import shutil


CHAT = Path(
    r"D:\serviceAi\app\application"
    r"\services\chat_service.py"
)

NLU = Path(
    r"D:\serviceAi\app\application"
    r"\services\nlu_core.py"
)

MARKER = "FOOD_CONVERSATION_V1"


def replace_once(
    text: str,
    old: str,
    new: str,
    label: str,
) -> str:
    if old not in text:
        raise RuntimeError(
            f"ANCHOR_NOT_FOUND: {label}"
        )

    return text.replace(
        old,
        new,
        1,
    )


chat_text = CHAT.read_text(
    encoding="utf-8-sig"
)

nlu_text = NLU.read_text(
    encoding="utf-8-sig"
)

if MARKER in chat_text:
    print("ALREADY_PATCHED")
    raise SystemExit(0)


chat_backup = CHAT.with_name(
    CHAT.name
    + ".bak_before_food_conversation_v1"
)

nlu_backup = NLU.with_name(
    NLU.name
    + ".bak_before_food_conversation_v1"
)

if not chat_backup.exists():
    shutil.copy2(
        CHAT,
        chat_backup,
    )

if not nlu_backup.exists():
    shutil.copy2(
        NLU,
        nlu_backup,
    )


# --------------------------------------------------
# 1. Food name from recent weekly menu
# --------------------------------------------------

chat_text = replace_once(
    chat_text,
    """        result = dict(nlu_result)

        is_food_follow_up = (
""",
    """        result = dict(nlu_result)

        # FOOD_CONVERSATION_V1
        food_follow_up_candidates = (
            self._find_food_candidates(
                text,
                conversation_payload,
            )
        )

        candidate_dates = {
            str(
                item.get(
                    "day",
                    {},
                ).get("date")
                or ""
            ).strip()
            for item in food_follow_up_candidates
            if isinstance(
                item,
                dict,
            )
            and str(
                item.get(
                    "day",
                    {},
                ).get("date")
                or ""
            ).strip()
        }

        unique_candidate_date = (
            next(
                iter(candidate_dates)
            )
            if len(candidate_dates) == 1
            else None
        )

        is_food_follow_up = (
""",
    "food candidate setup",
)


chat_text = replace_once(
    chat_text,
    """                or bool(
                    self._find_food_candidates(
                        text,
                        conversation_payload,
                    )
                )
""",
    """                or bool(
                    food_follow_up_candidates
                )
""",
    "food candidate reuse",
)


chat_text = replace_once(
    chat_text,
    """                self._infer_menu_date(
                    text,
                    conversation_payload,
                )
                or conversation_payload.get(
                    "activeDate"
                )
""",
    """                self._infer_menu_date(
                    text,
                    conversation_payload,
                )
                or unique_candidate_date
                or conversation_payload.get(
                    "activeDate"
                )
""",
    "first inferred date",
)


chat_text = replace_once(
    chat_text,
    """            or self._infer_menu_date(
                text,
                conversation_payload,
            )
            or conversation_payload.get(
                "activeDate"
            )
""",
    """            or self._infer_menu_date(
                text,
                conversation_payload,
            )
            or unique_candidate_date
            or conversation_payload.get(
                "activeDate"
            )
""",
    "second inferred date",
)


# --------------------------------------------------
# 2. No date means weekly menu, not today
# --------------------------------------------------

chat_text = replace_once(
    chat_text,
    """        target_date = (
            dates[0]
            if dates
            else (
                None
                if requested_weekday
                else (
                    conversation_payload.get(
                        "activeDate"
                    )
                    or context.date
                )
            )
        )
""",
    """        target_date = (
            dates[0]
            if dates
            else None
        )
""",
    "weekly menu default",
)


# --------------------------------------------------
# 3. Register/select/get means reserve
# --------------------------------------------------

chat_text = replace_once(
    chat_text,
    """        reservation_intent = any(
            keyword in text
            for keyword in [
                "رزرو",
                "برام بگیر",
                "برایم بگیر",
                "ثبت غذا",
                "سفارش بده",
            ]
        )
""",
    """        reservation_intent = any(
            keyword in text
            for keyword in [
                "رزرو",
                "ثبت",
                "انتخاب",
                "برام بگیر",
                "برایم بگیر",
                "بگیرش",
                "ثبتش کن",
                "ثبت شه",
                "ثبت شود",
                "انتخابش کن",
                "انتخاب شه",
                "انتخاب شود",
                "سفارش بده",
            ]
        )
""",
    "reservation synonyms",
)


# --------------------------------------------------
# 4. Colloquial menu phrases
# --------------------------------------------------

chat_text = replace_once(
    chat_text,
    """        menu_intent = any(
            keyword in text
            for keyword in [
                "منو",
                "نشان بده",
                "نمایش",
                "لیست",
                "چه غذایی",
                "غذاها",
            ]
        )
""",
    """        menu_intent = any(
            keyword in text
            for keyword in [
                "منو",
                "نشان بده",
                "نشون بده",
                "نشون",
                "نمایش",
                "لیست",
                "ببین",
                "بیار",
                "چه غذایی",
                "غذاها",
            ]
        )
""",
    "menu synonyms",
)


# --------------------------------------------------
# 5. NLU: ثبت غذا = رزرو غذا
# --------------------------------------------------

nlu_text = replace_once(
    nlu_text,
    """    if (
        has_food_word
        and has_reserve_word
    ):
        return "FOOD", "RESERVE_FOOD"
""",
    """    register_food_phrases = {
        "ثبت غذا",
        "غذا ثبت شه",
        "غذا ثبت شود",
        "غذا را ثبت کن",
        "غذا رو ثبت کن",
        "غذا انتخاب شه",
        "غذا انتخاب شود",
        "غذا را انتخاب کن",
        "غذا رو انتخاب کن",
    }

    if (
        has_food_word
        and (
            has_reserve_word
            or _contains_any_phrase(
                text,
                register_food_phrases,
            )
            or _contains_any_word(
                text,
                {
                    "ثبت",
                    "انتخاب",
                },
            )
        )
    ):
        return "FOOD", "RESERVE_FOOD"
""",
    "nlu register equals reserve",
)


try:
    CHAT.write_text(
        chat_text,
        encoding="utf-8",
    )

    NLU.write_text(
        nlu_text,
        encoding="utf-8",
    )

    py_compile.compile(
        str(CHAT),
        doraise=True,
    )

    py_compile.compile(
        str(NLU),
        doraise=True,
    )

except Exception:
    shutil.copy2(
        chat_backup,
        CHAT,
    )

    shutil.copy2(
        nlu_backup,
        NLU,
    )

    raise


print("PATCH_OK")
print(
    f"CHAT_BACKUP={chat_backup}"
)
print(
    f"NLU_BACKUP={nlu_backup}"
)