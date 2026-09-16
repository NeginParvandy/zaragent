from __future__ import annotations

import asyncio
import py_compile
import shutil
import sys
from pathlib import Path
from typing import Any


ROOT = Path(r"D:\serviceAi")
CHAT_FILE = (
    ROOT
    / "app"
    / "application"
    / "services"
    / "chat_service.py"
)

BACKUP_FILE = CHAT_FILE.with_name(
    "chat_service.py.bak_before_leave_context_sick_guard"
)

TEMP_BACKUP_FILE = CHAT_FILE.with_name(
    "chat_service.py.bak_leave_context_sick_guard_tmp"
)

MARKER = "LEAVE_CONTEXT_SICK_GUARD_V1"


def replace_once(
    source: str,
    old: str,
    new: str,
    label: str,
) -> str:
    count = source.count(old)

    if count != 1:
        raise RuntimeError(
            f"{label}: expected exactly one anchor, found {count}"
        )

    return source.replace(old, new, 1)


def apply_patch(source: str) -> str:
    if MARKER in source:
        return source

    old_create_block = '''            if intent in {
                "CREATE_LEAVE",
                "CREATE_MISSION",
            }:
                response = (
'''

    new_create_block = '''            if intent in {
                "CREATE_LEAVE",
                "CREATE_MISSION",
            }:
                # LEAVE_CONTEXT_SICK_GUARD_V1
                if (
                    intent == "CREATE_LEAVE"
                    and self._is_unsupported_sick_leave(
                        combined_text
                    )
                ):
                    await self._delete_conversation_state(
                        context
                    )

                    return {
                        "reply": (
                            "در حال حاضر دسترسی ثبت "
                            "مرخصی استعلاجی در این بخش "
                            "فعال نیست."
                        ),
                        "requiresConfirmation": False,
                    }

                response = (
'''

    source = replace_once(
        source,
        old_create_block,
        new_create_block,
        "create-leave guard anchor",
    )

    old_missing_type = '''        if not leave_type:
            return {
                "reply": (
                    "نوع درخواست را دقیق‌تر بگویید؛ "
                    "مانند مرخصی ساعتی، استحقاقی "
                    "یا مأموریت ساعتی."
                ),
                "requiresConfirmation": False,
            }
'''

    new_missing_type = '''        if not leave_type:
            return {
                "reply": (
                    "نوع درخواست را دقیق‌تر بگویید؛ "
                    "مانند مرخصی ساعتی، استحقاقی "
                    "یا مأموریت ساعتی."
                ),
                "requiresConfirmation": False,
                "data": {
                    "missingField": "requestType",
                },
            }
'''

    source = replace_once(
        source,
        old_missing_type,
        new_missing_type,
        "leave request-type anchor",
    )

    old_finalize_block = '''        updated_payload.update(
            {
                "nluState": (
                    nlu_result.get("state")
                    or {
                        "domain": (
                            nlu_result.get(
                                "domain"
                            )
                        ),
                        "intent": (
                            nlu_result.get(
                                "intent"
                            )
                        ),
                        "entities": (
                            nlu_result.get(
                                "entities"
                            )
                            or {}
                        ),
                        "missingFields": [],
                    }
                ),
                "originalMessage": (
                    combined_text
                ),
                "lastDomain": (
                    nlu_result.get("domain")
                ),
            }
        )

        data = response_data
'''

    new_finalize_block = '''        updated_payload.update(
            {
                "nluState": (
                    nlu_result.get("state")
                    or {
                        "domain": (
                            nlu_result.get(
                                "domain"
                            )
                        ),
                        "intent": (
                            nlu_result.get(
                                "intent"
                            )
                        ),
                        "entities": (
                            nlu_result.get(
                                "entities"
                            )
                            or {}
                        ),
                        "missingFields": [],
                    }
                ),
                "originalMessage": (
                    combined_text
                ),
                "lastDomain": (
                    nlu_result.get("domain")
                ),
            }
        )

        # LEAVE_CONTEXT_SICK_GUARD_V1
        response_missing_field = str(
            response_data.get(
                "missingField"
            )
            or ""
        ).strip()

        if response_missing_field:
            saved_nlu_state = dict(
                updated_payload.get(
                    "nluState"
                )
                or {}
            )

            saved_missing_fields = [
                str(item)
                for item in (
                    saved_nlu_state.get(
                        "missingFields"
                    )
                    or []
                )
                if str(item).strip()
            ]

            if (
                response_missing_field
                not in saved_missing_fields
            ):
                saved_missing_fields.append(
                    response_missing_field
                )

            saved_nlu_state[
                "missingFields"
            ] = saved_missing_fields

            updated_payload[
                "nluState"
            ] = saved_nlu_state

        data = response_data
'''

    source = replace_once(
        source,
        old_finalize_block,
        new_finalize_block,
        "finalize-state anchor",
    )

    old_helper_anchor = '''    def _looks_like_new_request(
        self,
        text: str,
    ) -> bool:
'''

    new_helper_anchor = '''    @staticmethod
    def _is_unsupported_sick_leave(
        text: str,
    ) -> bool:
        normalized = normalize_nlu_text(
            text or ""
        )

        return "استعلاجی" in normalized

    def _looks_like_new_request(
        self,
        text: str,
    ) -> bool:
'''

    source = replace_once(
        source,
        old_helper_anchor,
        new_helper_anchor,
        "sick-leave helper anchor",
    )

    return source


async def run_behavior_tests() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from app.application.services.chat_service import (
        ChatService,
    )

    continuation_payload = {
        "lastDomain": "LEAVE",
        "nluState": {
            "domain": "LEAVE",
            "intent": "CREATE_LEAVE",
            "entities": {
                "date": "1405/05/04",
                "startDate": "1405/05/04",
                "endDate": "1405/05/04",
            },
            "missingFields": [
                "requestType",
            ],
        },
    }

    assert ChatService._is_contextual_guard_continuation(
        "مرخصی استحقاقی",
        continuation_payload,
    )

    assert ChatService._is_unsupported_sick_leave(
        "مرخصی استعلاجی برای فردا"
    )

    assert not ChatService._is_unsupported_sick_leave(
        "مرخصی استحقاقی برای امروز"
    )

    service = object.__new__(ChatService)

    captured: dict[str, Any] = {}
    deleted = {
        "value": False,
    }

    async def fake_save(
        context: Any,
        payload: dict[str, Any],
    ) -> None:
        captured.clear()
        captured.update(payload)

    async def fake_delete(
        context: Any,
    ) -> None:
        deleted["value"] = True

    service._save_conversation_payload = fake_save
    service._delete_conversation_state = fake_delete

    nlu_result = {
        "domain": "LEAVE",
        "intent": "CREATE_LEAVE",
        "entities": {
            "date": "1405/05/04",
            "startDate": "1405/05/04",
            "endDate": "1405/05/04",
        },
        "state": {
            "domain": "LEAVE",
            "intent": "CREATE_LEAVE",
            "entities": {
                "date": "1405/05/04",
                "startDate": "1405/05/04",
                "endDate": "1405/05/04",
            },
            "missingFields": [],
        },
        "needsClarification": False,
        "conversationComplete": False,
    }

    response = {
        "reply": (
            "نوع درخواست را دقیق‌تر بگویید."
        ),
        "requiresConfirmation": False,
        "data": {
            "missingField": "requestType",
        },
    }

    result = await service._finalize_response_state(
        object(),
        nlu_result,
        {},
        response,
        "مرخصی ثبت کن برای امروز",
    )

    assert result is response
    assert not deleted["value"]

    saved_state = captured.get(
        "nluState"
    )

    assert isinstance(
        saved_state,
        dict,
    )

    assert saved_state.get(
        "intent"
    ) == "CREATE_LEAVE"

    assert saved_state.get(
        "missingFields"
    ) == ["requestType"]

    saved_entities = saved_state.get(
        "entities"
    )

    assert isinstance(
        saved_entities,
        dict,
    )

    assert saved_entities.get(
        "startDate"
    ) == "1405/05/04"


def main() -> None:
    if not CHAT_FILE.exists():
        raise FileNotFoundError(
            f"Chat service not found: {CHAT_FILE}"
        )

    original = CHAT_FILE.read_text(
        encoding="utf-8-sig"
    )

    if MARKER in original:
        py_compile.compile(
            str(CHAT_FILE),
            doraise=True,
        )

        asyncio.run(
            run_behavior_tests()
        )

        print("PATCH_ALREADY_APPLIED")
        print(
            "LEAVE_CONTEXT_SICK_GUARD_TESTS_OK"
        )
        return

    if not BACKUP_FILE.exists():
        shutil.copy2(
            CHAT_FILE,
            BACKUP_FILE,
        )

    shutil.copy2(
        CHAT_FILE,
        TEMP_BACKUP_FILE,
    )

    try:
        patched = apply_patch(
            original
        )

        CHAT_FILE.write_text(
            patched,
            encoding="utf-8-sig",
        )

        py_compile.compile(
            str(CHAT_FILE),
            doraise=True,
        )

        asyncio.run(
            run_behavior_tests()
        )

    except Exception:
        shutil.copy2(
            TEMP_BACKUP_FILE,
            CHAT_FILE,
        )

        print(
            "PATCH_FAILED_ROLLED_BACK"
        )
        raise

    finally:
        if TEMP_BACKUP_FILE.exists():
            TEMP_BACKUP_FILE.unlink()

    print("PATCH_OK")
    print(
        "LEAVE_CONTEXT_SICK_GUARD_TESTS_OK"
    )
    print(
        f"CHAT_BACKUP={BACKUP_FILE}"
    )


if __name__ == "__main__":
    main()