from __future__ import annotations

import asyncio
import importlib
import py_compile
import sys
import traceback
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(r"D:\serviceAi")

CHAT_FILE = (
    ROOT
    / "app"
    / "application"
    / "services"
    / "chat_service.py"
)

DEMO_FILE = (
    ROOT
    / "app"
    / "application"
    / "services"
    / "monthly_attendance_chat_demo.py"
)

CHAT_BACKUP = CHAT_FILE.with_name(
    "chat_service.py."
    "bak_before_monthly_attendance_chat_demo_v1"
)

MARKER = "MONTHLY_ATTENDANCE_CHAT_DEMO_V1"


DEMO_SOURCE = r'''from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(r"D:\serviceAi")

CARDS_DIR = (
    ROOT
    / "monthly_attendance_outputs"
)

STATE_DIR = (
    ROOT
    / "monthly_attendance_chat_states"
)

_LOCK = threading.Lock()

REPLAY_SECONDS = 15


START_PHRASES = (
    "گزارش تردد ماهانه",
    "گزارش ماهانه تردد",
    "گزارش کارکرد ماهانه",
    "بررسی تردد ماهانه",
    "گزارش حضور و غیاب ماهانه",
    "گزارش ماهانه حضور و غیاب",
)


CANCEL_PHRASES = {
    "لغو",
    "لغو گزارش",
    "بستن گزارش",
    "انصراف",
    "بیخیال",
    "بی خیال",
}


ALIASES = {
    "غیبت": "غیبت درست است",
    "غیبت درست": "غیبت درست است",
    "مرخصی درست": "مرخصی درست است",
    "تایید مرخصی": "مرخصی درست است",
    "تأیید مرخصی": "مرخصی درست است",
    "تایید تاخیر": "تأخیر درست است",
    "تأیید تاخیر": "تأخیر درست است",
    "تاخیر درست": "تأخیر درست است",
    "تأخیر درست": "تأخیر درست است",
    "ماموریت بودم": "مأموریت بودم",
    "ماموریت": "مأموریت بودم",
}


PERSIAN_DIGITS = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹",
    "0123456789",
)


def _utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def _normalize(value: Any) -> str:
    text = str(
        value or ""
    )

    text = text.translate(
        PERSIAN_DIGITS
    )

    text = (
        text.replace("ي", "ی")
        .replace("ك", "ک")
        .replace("\u200c", " ")
    )

    text = re.sub(
        r"[،,؛;.!؟?]+",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def _is_start(text: str) -> bool:
    normalized = _normalize(text)

    return any(
        phrase in normalized
        for phrase in START_PHRASES
    )


def _is_cancel(text: str) -> bool:
    return (
        _normalize(text)
        in CANCEL_PHRASES
    )


def _safe_identity(
    context: Any,
) -> str:
    employee_id = str(
        getattr(
            context,
            "employee_id",
            "",
        )
        or "unknown"
    ).strip()

    conversation_id = str(
        getattr(
            context,
            "conversation_id",
            "",
        )
        or "default"
    ).strip()

    digest = hashlib.sha256(
        (
            employee_id
            + "|"
            + conversation_id
        ).encode("utf-8")
    ).hexdigest()[:20]

    return digest


def _state_file(
    context: Any,
) -> Path:
    return (
        STATE_DIR
        / (
            "monthly_attendance_"
            f"{_safe_identity(context)}.json"
        )
    )


def _load_json(
    path: Path,
) -> dict[str, Any]:
    payload = json.loads(
        path.read_text(
            encoding="utf-8-sig"
        )
    )

    if not isinstance(
        payload,
        dict,
    ):
        raise ValueError(
            "ساختار فایل JSON معتبر نیست."
        )

    return payload


def _write_json_atomic(
    path: Path,
    payload: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = path.with_suffix(
        path.suffix + ".tmp"
    )

    temporary.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    temporary.replace(path)


def _latest_cards_file() -> Path:
    candidates = list(
        CARDS_DIR.glob(
            "monthly_attendance_cards_*.json"
        )
    )

    if not candidates:
        raise FileNotFoundError(
            "خروجی کارت گزارش ماهانه پیدا نشد."
        )

    return max(
        candidates,
        key=lambda item: (
            item.stat().st_mtime,
            item.name,
        ),
    )


def _issue_cards(
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    presentation = payload.get(
        "presentation"
    )

    if not isinstance(
        presentation,
        dict,
    ):
        return []

    cards = presentation.get(
        "issueCards"
    )

    if not isinstance(
        cards,
        list,
    ):
        return []

    return [
        item
        for item in cards
        if isinstance(
            item,
            dict,
        )
    ]


def _summary_card(
    payload: dict[str, Any],
) -> dict[str, Any]:
    presentation = payload.get(
        "presentation"
    )

    if not isinstance(
        presentation,
        dict,
    ):
        return {}

    summary = presentation.get(
        "summaryCard"
    )

    return (
        summary
        if isinstance(
            summary,
            dict,
        )
        else {}
    )


def _actions(
    card: dict[str, Any],
) -> list[dict[str, Any]]:
    interaction = card.get(
        "interaction"
    )

    if not isinstance(
        interaction,
        dict,
    ):
        return []

    actions = interaction.get(
        "actions"
    )

    if not isinstance(
        actions,
        list,
    ):
        return []

    return [
        item
        for item in actions
        if isinstance(
            item,
            dict,
        )
    ]


def _render_card(
    card: dict[str, Any],
) -> str:
    lines = [
        str(
            card.get(
                "progressText",
                "",
            )
        ),
        str(
            card.get(
                "title",
                "مورد نیازمند بررسی",
            )
        ),
        str(
            card.get(
                "subtitle",
                "",
            )
        ),
        str(
            card.get(
                "description",
                "",
            )
        ),
        "",
    ]

    facts = card.get(
        "facts"
    )

    if isinstance(
        facts,
        list,
    ):
        for fact in facts:
            if not isinstance(
                fact,
                dict,
            ):
                continue

            lines.append(
                "- "
                f"{fact.get('label', '')}: "
                f"{fact.get('value', '')}"
            )

    lines.append("")

    interaction = card.get(
        "interaction"
    )

    if isinstance(
        interaction,
        dict,
    ):
        lines.append(
            str(
                interaction.get(
                    "prompt",
                    "یک گزینه را انتخاب کنید.",
                )
            )
        )

    for index, action in enumerate(
        _actions(card),
        start=1,
    ):
        lines.append(
            f"{index}. "
            f"{action.get('label', '')}"
        )

    return "\n".join(lines).strip()


def _suggestions(
    card: dict[str, Any],
) -> list[str]:
    return [
        str(
            action.get(
                "label",
                "",
            )
        ).strip()
        for action in _actions(card)
        if str(
            action.get(
                "label",
                "",
            )
        ).strip()
    ]


def _build_state(
    cards_payload: dict[str, Any],
    source_file: Path,
) -> dict[str, Any]:
    cards = _issue_cards(
        cards_payload
    )

    return {
        "version": "1.0",
        "mode": (
            "chat-demo-read-only"
        ),
        "workflowId": str(
            cards_payload.get(
                "workflowId",
                "",
            )
        ),
        "sourceCards": str(
            source_file
        ),
        "period": (
            cards_payload.get(
                "period"
            )
            if isinstance(
                cards_payload.get(
                    "period"
                ),
                dict,
            )
            else {}
        ),
        "status": (
            "ACTIVE"
            if cards
            else "REVIEW_COMPLETE"
        ),
        "currentIndex": (
            0
            if cards
            else None
        ),
        "currentCardId": (
            str(
                cards[0].get(
                    "cardId",
                    "",
                )
            )
            if cards
            else None
        ),
        "totalCards": len(cards),
        "decisions": [],
        "createdAtUtc": _utc_now(),
        "updatedAtUtc": _utc_now(),
        "lastInput": None,
        "lastInputEpoch": None,
        "lastResponse": None,
        "policy": {
            "writesToHr": False,
            "automaticMutationAllowed": (
                False
            ),
            "mutationRequiresPreview": (
                True
            ),
            "mutationRequiresExplicitConfirmation": (
                True
            ),
        },
    }


def _current_card(
    cards: list[dict[str, Any]],
    state: dict[str, Any],
) -> dict[str, Any] | None:
    index = state.get(
        "currentIndex"
    )

    if not isinstance(
        index,
        int,
    ):
        return None

    if not 0 <= index < len(cards):
        return None

    return cards[index]


def _match_action(
    card: dict[str, Any],
    text: str,
) -> dict[str, Any] | None:
    actions = _actions(card)

    normalized = _normalize(
        text
    )

    if normalized.isdigit():
        number = int(
            normalized
        )

        if 1 <= number <= len(actions):
            return actions[
                number - 1
            ]

    alias_target = ALIASES.get(
        normalized
    )

    for action in actions:
        label = str(
            action.get(
                "label",
                "",
            )
        ).strip()

        normalized_label = (
            _normalize(label)
        )

        if normalized == normalized_label:
            return action

        if (
            alias_target
            and _normalize(
                alias_target
            )
            == normalized_label
        ):
            return action

    return None


def _start_response(
    cards_payload: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    cards = _issue_cards(
        cards_payload
    )

    summary = _summary_card(
        cards_payload
    )

    if not cards:
        return {
            "reply": (
                "گزارش تردد بررسی شد و "
                "مورد نیازمند پیگیری پیدا نشد."
            ),
            "requiresConfirmation": False,
            "suggestions": [],
            "data": {
                "feature": (
                    "monthlyAttendanceReview"
                ),
                "mode": (
                    "chat-demo-read-only"
                ),
                "workflow": state,
                "summaryCard": summary,
                "card": None,
                "writesToHr": False,
            },
        }

    card = cards[0]

    title = str(
        summary.get(
            "title",
            "گزارش تردد آماده بررسی است",
        )
    )

    body = str(
        summary.get(
            "body",
            "",
        )
    )

    reply = (
        f"{title}\n"
        f"{body}\n\n"
        f"{_render_card(card)}"
    ).strip()

    return {
        "reply": reply,
        "requiresConfirmation": False,
        "suggestions": (
            _suggestions(card)
        ),
        "data": {
            "feature": (
                "monthlyAttendanceReview"
            ),
            "mode": (
                "chat-demo-read-only"
            ),
            "workflowId": (
                state.get(
                    "workflowId"
                )
            ),
            "workflowStatus": (
                state.get(
                    "status"
                )
            ),
            "summaryCard": summary,
            "card": card,
            "writesToHr": False,
        },
    }


def _next_response(
    cards_payload: dict[str, Any],
    state: dict[str, Any],
    selected_label: str,
) -> dict[str, Any]:
    cards = _issue_cards(
        cards_payload
    )

    if (
        state.get("status")
        == "REVIEW_COMPLETE"
    ):
        decisions = state.get(
            "decisions"
        )

        if not isinstance(
            decisions,
            list,
        ):
            decisions = []

        selected_lines = [
            "- "
            f"{item.get('date', '')}: "
            f"{item.get('label', '')}"
            for item in decisions
            if isinstance(
                item,
                dict,
            )
        ]

        reply = (
            "بررسی گزارش ماهانه تمام شد.\n\n"
            + "\n".join(
                selected_lines
            )
            + (
                "\n\nتصمیم‌ها ذخیره شدند. "
                "در این نسخه نمایشی هیچ تغییری "
                "در سامانه منابع انسانی انجام نشد."
            )
        )

        return {
            "reply": reply.strip(),
            "requiresConfirmation": False,
            "suggestions": [
                "گزارش تردد ماهانه"
            ],
            "data": {
                "feature": (
                    "monthlyAttendanceReview"
                ),
                "mode": (
                    "chat-demo-read-only"
                ),
                "workflowId": (
                    state.get(
                        "workflowId"
                    )
                ),
                "workflowStatus": (
                    "REVIEW_COMPLETE"
                ),
                "decisions": decisions,
                "writesToHr": False,
            },
        }

    card = _current_card(
        cards,
        state,
    )

    if card is None:
        raise RuntimeError(
            "کارت بعدی گزارش پیدا نشد."
        )

    return {
        "reply": (
            f"ثبت شد: {selected_label}\n\n"
            f"{_render_card(card)}"
        ),
        "requiresConfirmation": False,
        "suggestions": (
            _suggestions(card)
        ),
        "data": {
            "feature": (
                "monthlyAttendanceReview"
            ),
            "mode": (
                "chat-demo-read-only"
            ),
            "workflowId": (
                state.get(
                    "workflowId"
                )
            ),
            "workflowStatus": (
                state.get(
                    "status"
                )
            ),
            "selectedLabel": (
                selected_label
            ),
            "card": card,
            "writesToHr": False,
        },
    }


def _replay_response(
    state: dict[str, Any],
    normalized_input: str,
) -> dict[str, Any] | None:
    if (
        state.get("lastInput")
        != normalized_input
    ):
        return None

    try:
        age = (
            time.time()
            - float(
                state.get(
                    "lastInputEpoch"
                )
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        return None

    response = state.get(
        "lastResponse"
    )

    if (
        0 <= age <= REPLAY_SECONDS
        and isinstance(
            response,
            dict,
        )
    ):
        return response

    return None


def _cache_response(
    state: dict[str, Any],
    normalized_input: str,
    response: dict[str, Any],
) -> None:
    state["lastInput"] = (
        normalized_input
    )

    state["lastInputEpoch"] = (
        time.time()
    )

    state["lastResponse"] = response
    state["updatedAtUtc"] = (
        _utc_now()
    )


async def handle_monthly_attendance_demo(
    context: Any,
    text: str,
) -> dict[str, Any] | None:
    normalized_input = (
        _normalize(text)
    )

    state_path = _state_file(
        context
    )

    with _LOCK:
        existing_state = None

        if state_path.exists():
            try:
                existing_state = (
                    _load_json(
                        state_path
                    )
                )

            except Exception:
                state_path.unlink(
                    missing_ok=True
                )

        if isinstance(
            existing_state,
            dict,
        ):
            replay = _replay_response(
                existing_state,
                normalized_input,
            )

            if replay is not None:
                return replay

        if _is_start(
            normalized_input
        ):
            source_file = (
                _latest_cards_file()
            )

            cards_payload = (
                _load_json(
                    source_file
                )
            )

            state = _build_state(
                cards_payload,
                source_file,
            )

            response = _start_response(
                cards_payload,
                state,
            )

            _cache_response(
                state,
                normalized_input,
                response,
            )

            _write_json_atomic(
                state_path,
                state,
            )

            return response

        if not isinstance(
            existing_state,
            dict,
        ):
            return None

        if _is_cancel(
            normalized_input
        ):
            state_path.unlink(
                missing_ok=True
            )

            return {
                "reply": (
                    "بررسی گزارش ماهانه بسته شد."
                ),
                "requiresConfirmation": False,
                "suggestions": [
                    "گزارش تردد ماهانه"
                ],
                "data": {
                    "feature": (
                        "monthlyAttendanceReview"
                    ),
                    "workflowStatus": (
                        "CANCELLED"
                    ),
                    "writesToHr": False,
                },
            }

        if (
            existing_state.get(
                "status"
            )
            != "ACTIVE"
        ):
            return None

        source_file = Path(
            str(
                existing_state.get(
                    "sourceCards",
                    "",
                )
            )
        )

        if not source_file.exists():
            source_file = (
                _latest_cards_file()
            )

        cards_payload = _load_json(
            source_file
        )

        cards = _issue_cards(
            cards_payload
        )

        card = _current_card(
            cards,
            existing_state,
        )

        if card is None:
            return None

        action = _match_action(
            card,
            normalized_input,
        )

        if action is None:
            return None

        payload = action.get(
            "payload"
        )

        if not isinstance(
            payload,
            dict,
        ):
            payload = {}

        decision = {
            "decisionId": (
                f"{card.get('cardId', '')}-"
                f"{action.get('actionId', '')}"
            ),
            "cardId": str(
                card.get(
                    "cardId",
                    "",
                )
            ),
            "date": str(
                payload.get(
                    "date",
                    "",
                )
            ),
            "weekday": str(
                payload.get(
                    "weekday",
                    "",
                )
            ),
            "issueType": str(
                payload.get(
                    "issueType",
                    "",
                )
            ),
            "label": str(
                action.get(
                    "label",
                    "",
                )
            ),
            "command": str(
                action.get(
                    "command",
                    "",
                )
            ),
            "nextStep": str(
                action.get(
                    "nextStep",
                    "",
                )
            ),
            "mayLeadToMutation": bool(
                action.get(
                    "mayLeadToMutation",
                    False,
                )
            ),
            "decisionStatus": (
                "AWAITING_PREVIEW"
                if action.get(
                    "mayLeadToMutation",
                    False,
                )
                else "RESOLVED"
            ),
            "selectedAtUtc": (
                _utc_now()
            ),
        }

        decisions = existing_state.get(
            "decisions"
        )

        if not isinstance(
            decisions,
            list,
        ):
            decisions = []

        if not any(
            isinstance(item, dict)
            and item.get("cardId")
            == decision["cardId"]
            for item in decisions
        ):
            decisions.append(
                decision
            )

        existing_state[
            "decisions"
        ] = decisions

        current_index = int(
            existing_state.get(
                "currentIndex",
                0,
            )
        )

        next_index = (
            current_index + 1
        )

        if next_index >= len(cards):
            existing_state[
                "status"
            ] = "REVIEW_COMPLETE"

            existing_state[
                "currentIndex"
            ] = None

            existing_state[
                "currentCardId"
            ] = None

        else:
            existing_state[
                "currentIndex"
            ] = next_index

            existing_state[
                "currentCardId"
            ] = str(
                cards[next_index].get(
                    "cardId",
                    "",
                )
            )

        selected_label = str(
            action.get(
                "label",
                "",
            )
        )

        response = _next_response(
            cards_payload,
            existing_state,
            selected_label,
        )

        _cache_response(
            existing_state,
            normalized_input,
            response,
        )

        _write_json_atomic(
            state_path,
            existing_state,
        )

        return response
'''


original_chat_bytes = (
    CHAT_FILE.read_bytes()
)

original_demo_bytes = (
    DEMO_FILE.read_bytes()
    if DEMO_FILE.exists()
    else None
)


try:
    chat_text = (
        original_chat_bytes.decode(
            "utf-8-sig"
        )
    )

    if not CHAT_BACKUP.exists():
        CHAT_BACKUP.write_bytes(
            original_chat_bytes
        )

    DEMO_FILE.write_text(
        DEMO_SOURCE,
        encoding="utf-8",
    )

    import_line = (
        "from app.application.services."
        "monthly_attendance_chat_demo "
        "import handle_monthly_attendance_demo\n"
    )

    if import_line not in chat_text:
        import_anchor = (
            "from app.application.services."
            "intent_guard import IntentGuard"
        )

        if (
            chat_text.count(
                import_anchor
            )
            != 1
        ):
            raise RuntimeError(
                "IMPORT_ANCHOR_NOT_FOUND_OR_DUPLICATED"
            )

        line_break = (
            "\r\n"
            if "\r\n" in chat_text
            else "\n"
        )

        chat_text = chat_text.replace(
            import_anchor,
            (
                import_anchor
                + line_break
                + import_line.rstrip(
                    "\r\n"
                )
            ),
            1,
        )

    handle_start = chat_text.find(
        "    async def handle("
    )

    if handle_start < 0:
        raise RuntimeError(
            "HANDLE_FUNCTION_NOT_FOUND"
        )

    next_method = chat_text.find(
        "\n    def ",
        handle_start + 1,
    )

    if next_method < 0:
        next_method = len(
            chat_text
        )

    handle_region = chat_text[
        handle_start:next_method
    ]

    if MARKER not in handle_region:
        candidate_positions = []

        for anchor in (
            "        pending_state_response =",
            "        intent_decision =",
        ):
            position = chat_text.find(
                anchor,
                handle_start,
                next_method,
            )

            if position >= 0:
                candidate_positions.append(
                    position
                )

        if not candidate_positions:
            raise RuntimeError(
                "HANDLE_INSERT_ANCHOR_NOT_FOUND"
            )

        insert_at = min(
            candidate_positions
        )

        prefix = chat_text[
            handle_start:insert_at
        ]

        if "text =" not in prefix:
            raise RuntimeError(
                "NORMALIZED_TEXT_NOT_FOUND_BEFORE_INSERT"
            )

        integration_block = f'''        # {MARKER}
        monthly_attendance_response = (
            await handle_monthly_attendance_demo(
                context,
                text,
            )
        )

        if (
            monthly_attendance_response
            is not None
        ):
            return monthly_attendance_response

'''

        chat_text = (
            chat_text[:insert_at]
            + integration_block
            + chat_text[insert_at:]
        )

    CHAT_FILE.write_text(
        chat_text,
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

    sys.path.insert(
        0,
        str(ROOT),
    )

    importlib.invalidate_caches()

    sys.modules.pop(
        (
            "app.application.services."
            "monthly_attendance_chat_demo"
        ),
        None,
    )

    demo_module = importlib.import_module(
        (
            "app.application.services."
            "monthly_attendance_chat_demo"
        )
    )

    async def smoke_test() -> None:
        fake_context = SimpleNamespace(
            employee_id=(
                "__monthly_patch_test__"
            ),
            conversation_id=(
                "__monthly_patch_test__"
            ),
        )

        state_path = (
            demo_module._state_file(
                fake_context
            )
        )

        state_path.unlink(
            missing_ok=True
        )

        start_response = (
            await demo_module
            .handle_monthly_attendance_demo(
                fake_context,
                "گزارش تردد ماهانه",
            )
        )

        if not isinstance(
            start_response,
            dict,
        ):
            raise RuntimeError(
                "START_RESPONSE_TEST_FAILED"
            )

        suggestions = (
            start_response.get(
                "suggestions"
            )
        )

        if not suggestions:
            raise RuntimeError(
                "START_SUGGESTIONS_TEST_FAILED"
            )

        selection_response = (
            await demo_module
            .handle_monthly_attendance_demo(
                fake_context,
                "4",
            )
        )

        if not isinstance(
            selection_response,
            dict,
        ):
            raise RuntimeError(
                "SELECTION_RESPONSE_TEST_FAILED"
            )

        state_path.unlink(
            missing_ok=True
        )

    asyncio.run(
        smoke_test()
    )

    final_chat_text = (
        CHAT_FILE.read_text(
            encoding="utf-8-sig"
        )
    )

    if (
        MARKER
        not in final_chat_text
    ):
        raise RuntimeError(
            "CHAT_MARKER_MISSING"
        )

    print("PATCH_OK")
    print(
        "SOURCE_SYNTAX_OK=True"
    )
    print(
        "MONTHLY_CHAT_DEMO_TEST_OK"
    )
    print(
        f"CHAT_BACKUP={CHAT_BACKUP}"
    )
    print(
        f"DEMO_MODULE={DEMO_FILE}"
    )

except Exception:
    CHAT_FILE.write_bytes(
        original_chat_bytes
    )

    if original_demo_bytes is None:
        DEMO_FILE.unlink(
            missing_ok=True
        )
    else:
        DEMO_FILE.write_bytes(
            original_demo_bytes
        )

    print(
        "PATCH_FAILED_ROLLED_BACK"
    )

    traceback.print_exc()
    raise