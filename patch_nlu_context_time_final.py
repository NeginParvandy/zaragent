# -*- coding: utf-8 -*-

from __future__ import annotations

import hashlib
import importlib
import py_compile
import re
import shutil
import sys
import traceback
from pathlib import Path


ROOT = Path(r"D:\serviceAi")

CHAT = (
    ROOT
    / "app"
    / "application"
    / "services"
    / "chat_service.py"
)

NLU = (
    ROOT
    / "app"
    / "application"
    / "services"
    / "nlu_core.py"
)

CHAT_BACKUP = CHAT.with_name(
    "chat_service.py.bak_before_nlu_context_time_final"
)

NLU_BACKUP = NLU.with_name(
    "nlu_core.py.bak_before_nlu_context_time_final"
)

CHAT_MARKER = "# CHAT_CONTEXT_TIME_FINAL_V1"
NLU_MARKER = "# NLU_CONTEXT_TIME_FINAL_V1"

EXPECTED_CHAT_SHA256 = (
    "a65a32ebb9afcd99e2c60f7932c6552d"
    "d52fd90fcc501061b1acd1b2f3e898eb"
)

EXPECTED_NLU_SHA256 = (
    "3b0dd1a3de00037f842c18444dccce69"
    "ff27be3e2b55d75ff465ec092659cbb3"
)


def file_sha256(
    content: bytes,
) -> str:
    return hashlib.sha256(
        content
    ).hexdigest()


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


def regex_replace_once(
    content: str,
    pattern: re.Pattern[str],
    replacement: str,
    label: str,
) -> str:
    updated, count = pattern.subn(
        replacement,
        content,
        count=1,
    )

    if count != 1:
        raise RuntimeError(
            f"{label}: expected 1 occurrence, "
            f"found {count}"
        )

    return updated


if not CHAT.exists():
    raise FileNotFoundError(CHAT)

if not NLU.exists():
    raise FileNotFoundError(NLU)


original_chat_bytes = CHAT.read_bytes()
original_nlu_bytes = NLU.read_bytes()

original_chat = original_chat_bytes.decode(
    "utf-8-sig"
)

original_nlu = original_nlu_bytes.decode(
    "utf-8-sig"
)


if (
    CHAT_MARKER in original_chat
    and NLU_MARKER in original_nlu
):
    print("ALREADY_PATCHED")
    raise SystemExit(0)


if (
    CHAT_MARKER in original_chat
    or NLU_MARKER in original_nlu
):
    raise RuntimeError(
        "Partial previous patch detected. "
        "Both files must be restored together."
    )


actual_chat_sha = file_sha256(
    original_chat_bytes
)

actual_nlu_sha = file_sha256(
    original_nlu_bytes
)


if actual_chat_sha != EXPECTED_CHAT_SHA256:
    raise RuntimeError(
        "chat_service.py changed after audit. "
        f"expected={EXPECTED_CHAT_SHA256} "
        f"actual={actual_chat_sha}"
    )


if actual_nlu_sha != EXPECTED_NLU_SHA256:
    raise RuntimeError(
        "nlu_core.py changed after audit. "
        f"expected={EXPECTED_NLU_SHA256} "
        f"actual={actual_nlu_sha}"
    )


chat_text = original_chat
nlu_text = original_nlu


NLU_EXTENSION = r'''

# NLU_CONTEXT_TIME_FINAL_V1
#
# This layer preserves the existing NLU implementation and adds:
# - strict domain isolation
# - common typo normalization
# - contextual short time parsing
# - morning/night clarification
# - safe handling of ambiguous attendance requests

_ORIGINAL_NORMALIZE_TEXT_CONTEXT_V1 = normalize_text
_ORIGINAL_ANALYZE_MESSAGE_CONTEXT_V1 = analyze_message


_CONTEXT_TYPO_REPLACEMENTS_V1 = {
    "اسحقاقی": "استحقاقی",
    "اسحقاقى": "استحقاقی",
    "ترد": "تردد",
    "یکشنیه": "یکشنبه",
    "یکشبه": "یکشنبه",
    "سهشنه": "سه شنبه",
    "سهشنیه": "سه شنبه",
    "چهارشنه": "چهارشنبه",
    "پنجشنه": "پنجشنبه",
}


_CONTEXT_MERIDIEM_V1 = {
    "صبح": "AM",
    "بامداد": "AM",
    "ظهر": "PM",
    "بعدازظهر": "PM",
    "بعد از ظهر": "PM",
    "عصر": "PM",
    "شب": "PM",
}


_CONTEXT_SMALL_NUMBERS_V1 = {
    "صفر": 0,
    "یک": 1,
    "دو": 2,
    "سه": 3,
    "چهار": 4,
    "پنج": 5,
    "شش": 6,
    "هفت": 7,
    "هشت": 8,
    "نه": 9,
    "ده": 10,
    "یازده": 11,
    "دوازده": 12,
    "سیزده": 13,
    "چهارده": 14,
    "پانزده": 15,
    "شانزده": 16,
    "هفده": 17,
    "هجده": 18,
    "نوزده": 19,
}


_CONTEXT_TENS_V1 = {
    "بیست": 20,
    "سی": 30,
    "چهل": 40,
    "پنجاه": 50,
}


def _context_replace_exact_word_v1(
    text: str,
    old: str,
    new: str,
) -> str:
    return re.sub(
        (
            r"(?<![A-Za-z0-9_\u0600-\u06FF])"
            + re.escape(old)
            + r"(?![A-Za-z0-9_\u0600-\u06FF])"
        ),
        new,
        text,
    )


def normalize_text(
    value: Any,
) -> str:
    text = (
        _ORIGINAL_NORMALIZE_TEXT_CONTEXT_V1(
            value
        )
    )

    for old, new in (
        _CONTEXT_TYPO_REPLACEMENTS_V1.items()
    ):
        text = _context_replace_exact_word_v1(
            text,
            old,
            new,
        )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def _context_tokens_v1(
    text: str,
) -> set[str]:
    return set(
        re.findall(
            (
                r"[A-Za-z]+|"
                r"[0-9]+|"
                r"[\u0600-\u06FF]+"
            ),
            normalize_text(text),
        )
    )


def _context_explicit_domain_v1(
    text: str,
) -> str | None:
    tokens = _context_tokens_v1(
        text
    )

    if "ماموریت" in tokens:
        return "MISSION"

    if "مرخصی" in tokens:
        return "LEAVE"

    if tokens.intersection(
        {
            "تردد",
            "ورود",
            "خروج",
            "ساعتزنی",
        }
    ):
        return "ATTENDANCE"

    if tokens.intersection(
        {
            "غذا",
            "غذای",
            "منو",
            "ناهار",
            "رستوران",
        }
    ):
        return "FOOD"

    return None


def _context_parse_number_words_v1(
    value: str,
) -> int | None:
    normalized = normalize_text(
        value
    )

    if normalized.isdigit():
        return int(normalized)

    if normalized in (
        _CONTEXT_SMALL_NUMBERS_V1
    ):
        return (
            _CONTEXT_SMALL_NUMBERS_V1[
                normalized
            ]
        )

    if normalized in _CONTEXT_TENS_V1:
        return _CONTEXT_TENS_V1[
            normalized
        ]

    parts = [
        part.strip()
        for part in normalized.split(
            " و "
        )
        if part.strip()
    ]

    if len(parts) != 2:
        return None

    tens = _CONTEXT_TENS_V1.get(
        parts[0]
    )

    unit = (
        _CONTEXT_SMALL_NUMBERS_V1.get(
            parts[1]
        )
    )

    if (
        tens is None
        or unit is None
        or not 0 <= unit <= 9
    ):
        return None

    return tens + unit


def _context_parse_short_time_v1(
    text: str,
) -> tuple[
    int,
    int,
    str | None,
] | None:
    normalized = normalize_text(
        text
    )

    meridiem = None

    for phrase, value in sorted(
        _CONTEXT_MERIDIEM_V1.items(),
        key=lambda item: len(
            item[0]
        ),
        reverse=True,
    ):
        if normalized == phrase:
            return None

        suffix = " " + phrase

        if normalized.endswith(
            suffix
        ):
            meridiem = value

            normalized = normalized[
                :-len(suffix)
            ].strip()

            break

    normalized = re.sub(
        r"^ساعت\s+",
        "",
        normalized,
    ).strip()

    match = re.fullmatch(
        (
            r"(?P<hour>[0-9]{1,2})"
            r"(?:\s+و\s+"
            r"(?P<minute>.+?))?"
        ),
        normalized,
    )

    if not match:
        return None

    hour = int(
        match.group("hour")
    )

    if not 0 <= hour <= 23:
        return None

    minute_text = str(
        match.group("minute")
        or ""
    ).strip()

    if not minute_text:
        minute = 0

    else:
        minute_text = re.sub(
            r"\s+دقیقه$",
            "",
            minute_text,
        ).strip()

        if minute_text == "نیم":
            minute = 30

        elif minute_text == "ربع":
            minute = 15

        elif minute_text == "سه ربع":
            minute = 45

        else:
            parsed_minute = (
                _context_parse_number_words_v1(
                    minute_text
                )
            )

            if parsed_minute is None:
                return None

            minute = parsed_minute

    if not 0 <= minute <= 59:
        return None

    return (
        hour,
        minute,
        meridiem,
    )


def _context_apply_meridiem_v1(
    hour: int,
    meridiem: str,
) -> int:
    if meridiem == "AM":
        if hour == 12:
            return 0

        return hour

    if meridiem == "PM":
        if hour >= 12:
            return hour

        return hour + 12

    return hour


def _context_attendance_result_v1(
    previous_state: dict[str, Any],
    *,
    hour: int,
    minute: int,
    meridiem: str | None,
) -> dict[str, Any] | None:
    previous_domain = str(
        previous_state.get(
            "domain"
        )
        or ""
    )

    previous_intent = str(
        previous_state.get(
            "intent"
        )
        or ""
    )

    if (
        previous_domain
        != "ATTENDANCE"
        or previous_intent
        != "CREATE_TIME_EVENT"
    ):
        return None

    previous_entities = (
        previous_state.get(
            "entities"
        )
        if isinstance(
            previous_state.get(
                "entities"
            ),
            dict,
        )
        else {}
    )

    entities = dict(
        previous_entities
    )

    previous_missing = (
        previous_state.get(
            "missingFields"
        )
        if isinstance(
            previous_state.get(
                "missingFields"
            ),
            list,
        )
        else []
    )

    missing_fields = [
        str(item)
        for item in previous_missing
        if str(item)
        not in {
            "time",
            "meridiem",
        }
    ]

    if (
        meridiem is None
        and 1 <= hour <= 12
    ):
        entities.pop(
            "time",
            None,
        )

        entities[
            "ambiguousHour"
        ] = hour

        entities[
            "ambiguousMinute"
        ] = minute

        missing_fields = [
            "meridiem",
            *[
                item
                for item in missing_fields
                if item != "meridiem"
            ],
        ]

        if minute == 0:
            time_label = str(hour)

        elif minute == 30:
            time_label = (
                f"{hour} و نیم"
            )

        else:
            time_label = (
                f"{hour} و {minute} دقیقه"
            )

        clarification = (
            f"منظورتان ساعت "
            f"{time_label} صبح است "
            f"یا ساعت {time_label} شب؟"
        )

    else:
        resolved_hour = hour

        if meridiem is not None:
            resolved_hour = (
                _context_apply_meridiem_v1(
                    hour,
                    meridiem,
                )
            )

        entities["time"] = (
            f"{resolved_hour:02d}:"
            f"{minute:02d}"
        )

        entities.pop(
            "ambiguousHour",
            None,
        )

        entities.pop(
            "ambiguousMinute",
            None,
        )

        if "eventType" in missing_fields:
            clarification = (
                "این تردد مربوط به "
                "ورود است یا خروج؟"
            )

        else:
            clarification = None

    state = {
        "domain": "ATTENDANCE",
        "intent": (
            "CREATE_TIME_EVENT"
        ),
        "entities": entities,
        "missingFields": (
            missing_fields
        ),
    }

    return {
        "domain": "ATTENDANCE",
        "intent": (
            "CREATE_TIME_EVENT"
        ),
        "entities": entities,
        "confidence": 1.0,
        "missingFields": (
            missing_fields
        ),
        "needsClarification": bool(
            missing_fields
        ),
        "conversationComplete": (
            not missing_fields
        ),
        "clarification": (
            clarification
        ),
        "errors": [],
        "state": state,
    }


def _context_meridiem_reply_v1(
    text: str,
    previous_state: dict[str, Any],
) -> dict[str, Any] | None:
    normalized = normalize_text(
        text
    )

    meridiem = (
        _CONTEXT_MERIDIEM_V1.get(
            normalized
        )
    )

    if meridiem is None:
        return None

    previous_entities = (
        previous_state.get(
            "entities"
        )
        if isinstance(
            previous_state.get(
                "entities"
            ),
            dict,
        )
        else {}
    )

    raw_hour = (
        previous_entities.get(
            "ambiguousHour"
        )
    )

    if raw_hour is None:
        return None

    try:
        hour = int(raw_hour)

        minute = int(
            previous_entities.get(
                "ambiguousMinute"
            )
            or 0
        )

    except (
        TypeError,
        ValueError,
    ):
        return None

    return (
        _context_attendance_result_v1(
            previous_state,
            hour=hour,
            minute=minute,
            meridiem=meridiem,
        )
    )


def _context_postprocess_leave_v1(
    normalized: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    if (
        result.get("domain")
        != "LEAVE"
        or result.get("intent")
        != "LEAVE_UNKNOWN"
    ):
        return result

    tokens = _context_tokens_v1(
        normalized
    )

    has_leave_type = bool(
        tokens.intersection(
            {
                "استحقاقی",
                "استعلاجی",
                "ساعتی",
                "روزانه",
            }
        )
    )

    entities_value = result.get(
        "entities"
    )

    entities = (
        dict(entities_value)
        if isinstance(
            entities_value,
            dict,
        )
        else {}
    )

    has_date = bool(
        entities.get("startDate")
        or entities.get("date")
    )

    if not (
        "مرخصی" in tokens
        and has_leave_type
        and has_date
    ):
        return result

    updated = dict(result)

    updated["intent"] = (
        "CREATE_LEAVE"
    )

    updated[
        "missingFields"
    ] = []

    updated[
        "needsClarification"
    ] = False

    updated[
        "conversationComplete"
    ] = False

    updated[
        "clarification"
    ] = None

    updated[
        "confidence"
    ] = max(
        float(
            updated.get(
                "confidence"
            )
            or 0
        ),
        0.95,
    )

    updated["state"] = {
        "domain": "LEAVE",
        "intent": (
            "CREATE_LEAVE"
        ),
        "entities": entities,
        "missingFields": [],
    }

    return updated


def _context_postprocess_attendance_v1(
    normalized: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    if (
        result.get("domain")
        != "ATTENDANCE"
        or result.get("intent")
        != "SHOW_ATTENDANCE"
    ):
        return result

    read_terms = (
        "نشان بده",
        "نمایش",
        "سوابق",
        "گزارش",
        "لیست",
        "ببین",
        "بررسی کن",
        "چه ترددی",
        "چند تردد",
    )

    create_terms = (
        "ثبت",
        "بزن",
        "ایجاد",
        "درج",
        "ساعت بزن",
    )

    if any(
        term in normalized
        for term in read_terms
    ):
        return result

    if any(
        term in normalized
        for term in create_terms
    ):
        return result

    entities_value = result.get(
        "entities"
    )

    entities = (
        dict(entities_value)
        if isinstance(
            entities_value,
            dict,
        )
        else {}
    )

    if not (
        entities.get("date")
        and any(
            term in normalized
            for term in (
                "تردد",
                "ورود",
                "خروج",
            )
        )
    ):
        return result

    updated = dict(result)

    updated["intent"] = (
        "ATTENDANCE_UNKNOWN"
    )

    updated[
        "missingFields"
    ] = ["intent"]

    updated[
        "needsClarification"
    ] = True

    updated[
        "conversationComplete"
    ] = False

    updated[
        "clarification"
    ] = (
        "می‌خواهید تردد این تاریخ "
        "را ثبت کنید یا سوابق تردد "
        "را ببینید؟"
    )

    updated[
        "confidence"
    ] = max(
        float(
            updated.get(
                "confidence"
            )
            or 0
        ),
        0.9,
    )

    updated["state"] = {
        "domain": "ATTENDANCE",
        "intent": (
            "ATTENDANCE_UNKNOWN"
        ),
        "entities": entities,
        "missingFields": [
            "intent"
        ],
    }

    return updated


def analyze_message(
    message: str,
    *,
    reference_date: str,
    conversation_state: (
        dict[str, Any]
        | None
    ) = None,
) -> dict[str, Any]:
    normalized = normalize_text(
        message
    )

    previous_state = (
        dict(conversation_state)
        if isinstance(
            conversation_state,
            dict,
        )
        else {}
    )

    explicit_domain = (
        _context_explicit_domain_v1(
            normalized
        )
    )

    previous_domain = str(
        previous_state.get(
            "domain"
        )
        or ""
    )

    # A clearly named new domain always wins.
    if (
        explicit_domain
        and previous_domain
        and explicit_domain
        != previous_domain
    ):
        previous_state = {}

    if previous_state:
        meridiem_result = (
            _context_meridiem_reply_v1(
                normalized,
                previous_state,
            )
        )

        if meridiem_result is not None:
            return meridiem_result

        parsed_short_time = (
            _context_parse_short_time_v1(
                normalized
            )
        )

        if parsed_short_time is not None:
            (
                hour,
                minute,
                meridiem,
            ) = parsed_short_time

            attendance_result = (
                _context_attendance_result_v1(
                    previous_state,
                    hour=hour,
                    minute=minute,
                    meridiem=meridiem,
                )
            )

            if attendance_result is not None:
                return attendance_result

    result = (
        _ORIGINAL_ANALYZE_MESSAGE_CONTEXT_V1(
            normalized,
            reference_date=(
                reference_date
            ),
            conversation_state=(
                previous_state
                if previous_state
                else None
            ),
        )
    )

    if not isinstance(
        result,
        dict,
    ):
        return result

    # Defensive retry without old state if an explicit
    # new domain was routed somewhere else.
    if (
        explicit_domain
        and result.get("domain")
        != explicit_domain
    ):
        clean_result = (
            _ORIGINAL_ANALYZE_MESSAGE_CONTEXT_V1(
                normalized,
                reference_date=(
                    reference_date
                ),
                conversation_state=None,
            )
        )

        if isinstance(
            clean_result,
            dict,
        ):
            result = clean_result

    result = (
        _context_postprocess_leave_v1(
            normalized,
            result,
        )
    )

    result = (
        _context_postprocess_attendance_v1(
            normalized,
            result,
        )
    )

    return result
'''


CHAT_HELPER = r'''    @staticmethod
    def _is_contextual_guard_continuation(
        text: str,
        conversation_payload: dict[str, Any],
    ) -> bool:
        if not isinstance(
            conversation_payload,
            dict,
        ):
            return False

        if str(
            conversation_payload.get(
                "pendingActionId"
            )
            or ""
        ).strip():
            return True

        state = (
            conversation_payload.get(
                "nluState"
            )
            if isinstance(
                conversation_payload.get(
                    "nluState"
                ),
                dict,
            )
            else {}
        )

        domain = str(
            state.get("domain")
            or conversation_payload.get(
                "lastDomain"
            )
            or ""
        ).strip()

        if domain in {
            "",
            "UNKNOWN",
            "OUT_OF_SCOPE",
        }:
            return False

        missing_fields = (
            state.get(
                "missingFields"
            )
            if isinstance(
                state.get(
                    "missingFields"
                ),
                list,
            )
            else []
        )

        if not missing_fields:
            return False

        normalized = (
            normalize_nlu_text(
                text
            )
        )

        if not normalized:
            return False

        if re.search(
            r"[A-Za-z]",
            normalized,
        ):
            return False

        tokens = re.findall(
            (
                r"[0-9]+|"
                r"[\u0600-\u06FF]+"
            ),
            normalized,
        )

        if len(tokens) > 8:
            return False

        continuation_terms = {
            "صبح",
            "بامداد",
            "ظهر",
            "بعدازظهر",
            "عصر",
            "شب",
            "نیم",
            "ربع",
            "دقیقه",
            "ساعت",
            "امروز",
            "فردا",
            "پس",
            "روز",
            "ماه",
            "فروردین",
            "اردیبهشت",
            "خرداد",
            "تیر",
            "مرداد",
            "شهریور",
            "مهر",
            "آبان",
            "آذر",
            "دی",
            "بهمن",
            "اسفند",
            "ورود",
            "خروج",
            "استحقاقی",
            "استعلاجی",
            "ساعتی",
            "بله",
            "آره",
            "نه",
            "لغو",
            "تایید",
            "تأیید",
        }

        if any(
            token.isdigit()
            or token
            in continuation_terms
            for token in tokens
        ):
            return True

        # A short Persian reply is accepted only
        # while the agent is waiting for a field.
        return (
            bool(tokens)
            and len(tokens) <= 3
        )

'''


try:
    if not CHAT_BACKUP.exists():
        shutil.copy2(
            CHAT,
            CHAT_BACKUP,
        )

    if not NLU_BACKUP.exists():
        shutil.copy2(
            NLU,
            NLU_BACKUP,
        )

    # Add the compatibility layer to NLU.
    nlu_text = (
        nlu_text.rstrip()
        + NLU_EXTENSION
        + "\n"
    )

    # Three-minute conversational memory.
    chat_text = replace_once(
        chat_text,
        (
            "FOOD_CHAT_STATE_TTL_MINUTES "
            "= 10"
        ),
        (
            "FOOD_CHAT_STATE_TTL_MINUTES "
            "= 3"
        ),
        "food chat TTL",
    )

    chat_text = replace_once(
        chat_text,
        (
            "CONVERSATION_STATE_TTL_MINUTES "
            "= 30"
        ),
        (
            "CONVERSATION_STATE_TTL_MINUTES "
            "= 3"
        ),
        "conversation TTL",
    )

    # Use canonical NLU normalization before routing.
    chat_text = replace_once(
        chat_text,
        "        text = normalize_persian_text(message)",
        (
            f"        {CHAT_MARKER}\n"
            "        text = normalize_nlu_text(\n"
            "            normalize_persian_text(\n"
            "                message\n"
            "            )\n"
            "        )"
        ),
        "chat message normalization",
    )

    # Consult active conversation state before rejecting
    # a short response such as "8" or "صبح".
    # Load active conversation state before rejecting
    # a short contextual reply such as "8" or "صبح".
    chat_had_trailing_newline = (
        chat_text.endswith("\n")
    )

    guard_lines = (
        chat_text.splitlines()
    )

    guard_indexes = [
        index
        for index, line in enumerate(
            guard_lines
        )
        if line.strip()
        == "if not intent_decision.allowed:"
    ]

    if len(guard_indexes) != 1:
        raise RuntimeError(
            "context-aware IntentGuard: "
            "expected exactly one guard condition, "
            f"found {len(guard_indexes)}"
        )

    guard_index = guard_indexes[0]

    return_index = next(
        (
            index
            for index in range(
                guard_index + 1,
                min(
                    len(guard_lines),
                    guard_index + 8,
                ),
            )
            if guard_lines[index].strip()
            == (
                "return "
                "intent_decision.to_response()"
            )
        ),
        None,
    )

    if return_index is None:
        raise RuntimeError(
            "IntentGuard rejection return "
            "was not found"
        )

    guard_indent = (
        guard_lines[guard_index][
            :len(
                guard_lines[guard_index]
            )
            - len(
                guard_lines[
                    guard_index
                ].lstrip()
            )
        ]
    )

    inner_indent = (
        guard_indent + "    "
    )

    nested_indent = (
        inner_indent + "    "
    )

    replacement_lines = [
        (
            guard_indent
            + "if not "
            + "intent_decision.allowed:"
        ),
        (
            inner_indent
            + "guard_payload = ("
        ),
        (
            nested_indent
            + "await self."
            + "_load_conversation_payload("
        ),
        (
            nested_indent
            + "    context"
        ),
        (
            nested_indent
            + ")"
        ),
        (
            inner_indent
            + ")"
        ),
        "",
        (
            inner_indent
            + "if not self."
            + "_is_contextual_guard_continuation("
        ),
        (
            nested_indent
            + "text,"
        ),
        (
            nested_indent
            + "guard_payload,"
        ),
        (
            inner_indent
            + "):"
        ),
        (
            nested_indent
            + "return "
            + "intent_decision.to_response()"
        ),
    ]

    guard_lines[
        guard_index:return_index + 1
    ] = replacement_lines

    chat_text = "\n".join(
        guard_lines
    )

    if chat_had_trailing_newline:
        chat_text += "\n"


    helper_anchor = (
        "    def _confirmation_replay_response(\n"
    )

    chat_text = replace_once(
        chat_text,
        helper_anchor,
        CHAT_HELPER + helper_anchor,
        "chat contextual helper anchor",
    )

    NLU.write_text(
        nlu_text,
        encoding="utf-8",
    )

    CHAT.write_text(
        chat_text,
        encoding="utf-8",
    )

    py_compile.compile(
        str(NLU),
        doraise=True,
    )

    py_compile.compile(
        str(CHAT),
        doraise=True,
    )

    sys.path.insert(
        0,
        str(ROOT),
    )

    for module_name in (
        "app.application.services.chat_service",
        "app.application.services.nlu_core",
    ):
        sys.modules.pop(
            module_name,
            None,
        )

    importlib.invalidate_caches()

    nlu = importlib.import_module(
        "app.application.services.nlu_core"
    )

    analyze = nlu.analyze_message
    normalize = nlu.normalize_text

    reference_date = "1405/05/02"

    # ---------------------------------------------
    # Normalization tests
    # ---------------------------------------------

    if normalize(
        "مرخصی اسحقاقی برای فردا"
    ) != (
        "مرخصی استحقاقی برای فردا"
    ):
        raise RuntimeError(
            "Leave typo normalization failed"
        )

    if normalize(
        "ثبت ترد برای فردا"
    ) != (
        "ثبت تردد برای فردا"
    ):
        raise RuntimeError(
            "Attendance typo normalization failed"
        )

    # ---------------------------------------------
    # Domain isolation tests
    # ---------------------------------------------

    food_state = {
        "domain": "FOOD",
        "intent": "RESERVE_FOOD",
        "entities": {
            "date": "1405/05/03",
        },
        "missingFields": [
            "food",
        ],
    }

    leave_result = analyze(
        "مرخصی اسحقاقی برای فردا",
        reference_date=(
            reference_date
        ),
        conversation_state=(
            food_state
        ),
    )

    if (
        leave_result.get("domain")
        != "LEAVE"
        or leave_result.get(
            "intent"
        )
        != "CREATE_LEAVE"
        or leave_result.get(
            "needsClarification"
        )
    ):
        raise RuntimeError(
            "Leave domain isolation failed: "
            f"{leave_result!r}"
        )

    attendance_result = analyze(
        "ثبت ترد برای فردا",
        reference_date=(
            reference_date
        ),
        conversation_state=None,
    )

    if (
        attendance_result.get(
            "domain"
        )
        != "ATTENDANCE"
        or attendance_result.get(
            "intent"
        )
        != "CREATE_TIME_EVENT"
    ):
        raise RuntimeError(
            "Attendance typo test failed: "
            f"{attendance_result!r}"
        )

    # ---------------------------------------------
    # Contextual time tests
    # ---------------------------------------------

    attendance_state = {
        "domain": "ATTENDANCE",
        "intent": (
            "CREATE_TIME_EVENT"
        ),
        "entities": {
            "date": "1405/05/03",
        },
        "missingFields": [
            "time",
            "eventType",
        ],
    }

    bare_hour = analyze(
        "۸",
        reference_date=(
            reference_date
        ),
        conversation_state=(
            attendance_state
        ),
    )

    if (
        bare_hour.get("domain")
        != "ATTENDANCE"
        or not bare_hour.get(
            "needsClarification"
        )
        or "صبح"
        not in str(
            bare_hour.get(
                "clarification"
            )
            or ""
        )
        or "شب"
        not in str(
            bare_hour.get(
                "clarification"
            )
            or ""
        )
        or (
            bare_hour.get(
                "entities"
            )
            or {}
        ).get(
            "ambiguousHour"
        )
        != 8
    ):
        raise RuntimeError(
            "Bare-hour clarification failed: "
            f"{bare_hour!r}"
        )

    morning_result = analyze(
        "صبح",
        reference_date=(
            reference_date
        ),
        conversation_state=(
            bare_hour.get(
                "state"
            )
        ),
    )

    if (
        morning_result.get(
            "domain"
        )
        != "ATTENDANCE"
        or (
            morning_result.get(
                "entities"
            )
            or {}
        ).get("time")
        != "08:00"
    ):
        raise RuntimeError(
            "Morning continuation failed: "
            f"{morning_result!r}"
        )

    time_cases = {
        "8 صبح": "08:00",
        "8 شب": "20:00",
        "8 و نیم صبح": "08:30",
        "8 و نیم شب": "20:30",
        (
            "8 و چهل و پنج دقیقه صبح"
        ): "08:45",
        (
            "8 و چهل و پنج دقیقه شب"
        ): "20:45",
        (
            "10 و پنجاه دقیقه شب"
        ): "22:50",
        "20 و 15 دقیقه": "20:15",
    }

    for message, expected_time in (
        time_cases.items()
    ):
        result = analyze(
            message,
            reference_date=(
                reference_date
            ),
            conversation_state=(
                attendance_state
            ),
        )

        actual_time = (
            result.get("entities")
            or {}
        ).get("time")

        if (
            result.get("domain")
            != "ATTENDANCE"
            or actual_time
            != expected_time
        ):
            raise RuntimeError(
                "Time parsing failed for "
                f"{message!r}: {result!r}"
            )

    half_ambiguous = analyze(
        "8 و نیم",
        reference_date=(
            reference_date
        ),
        conversation_state=(
            attendance_state
        ),
    )

    if (
        (
            half_ambiguous.get(
                "entities"
            )
            or {}
        ).get(
            "ambiguousMinute"
        )
        != 30
        or "صبح"
        not in str(
            half_ambiguous.get(
                "clarification"
            )
            or ""
        )
        or "شب"
        not in str(
            half_ambiguous.get(
                "clarification"
            )
            or ""
        )
    ):
        raise RuntimeError(
            "Ambiguous half-hour failed: "
            f"{half_ambiguous!r}"
        )

    # ---------------------------------------------
    # Persian date and domain-switch test
    # ---------------------------------------------

    date_result = analyze(
        (
            "ثبت مرخصی استحقاقی "
            "برای ۴ مرداد"
        ),
        reference_date=(
            reference_date
        ),
        conversation_state=(
            attendance_state
        ),
    )

    if (
        date_result.get("domain")
        != "LEAVE"
        or date_result.get("intent")
        != "CREATE_LEAVE"
        or (
            date_result.get(
                "entities"
            )
            or {}
        ).get("startDate")
        != "1405/05/04"
    ):
        raise RuntimeError(
            "Persian date/domain switch failed: "
            f"{date_result!r}"
        )

    # ---------------------------------------------
    # Ambiguous attendance must ask, not read data.
    # ---------------------------------------------

    ambiguous_attendance = analyze(
        "تردد برای فردا",
        reference_date=(
            reference_date
        ),
        conversation_state=None,
    )

    if (
        ambiguous_attendance.get(
            "domain"
        )
        != "ATTENDANCE"
        or ambiguous_attendance.get(
            "intent"
        )
        != "ATTENDANCE_UNKNOWN"
        or not ambiguous_attendance.get(
            "needsClarification"
        )
    ):
        raise RuntimeError(
            "Ambiguous attendance was not "
            "clarified: "
            f"{ambiguous_attendance!r}"
        )

    chat_module = importlib.import_module(
        "app.application.services.chat_service"
    )

    if (
        chat_module
        .CONVERSATION_STATE_TTL_MINUTES
        != 3
    ):
        raise RuntimeError(
            "Conversation TTL is not 3 minutes"
        )

    if (
        chat_module
        .FOOD_CHAT_STATE_TTL_MINUTES
        != 3
    ):
        raise RuntimeError(
            "Food chat TTL is not 3 minutes"
        )

    if CHAT_MARKER not in chat_text:
        raise RuntimeError(
            "Chat marker missing"
        )

    if NLU_MARKER not in nlu_text:
        raise RuntimeError(
            "NLU marker missing"
        )

    print("PATCH_OK")
    print(
        "NLU_CONTEXT_TIME_TESTS_OK"
    )
    print(
        f"CHAT_BACKUP={CHAT_BACKUP}"
    )
    print(
        f"NLU_BACKUP={NLU_BACKUP}"
    )

except Exception:
    CHAT.write_bytes(
        original_chat_bytes
    )

    NLU.write_bytes(
        original_nlu_bytes
    )

    print(
        "PATCH_FAILED_ROLLED_BACK"
    )

    traceback.print_exc()
    raise