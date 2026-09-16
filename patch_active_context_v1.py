from pathlib import Path
import py_compile
import shutil
import sys

ROOT = Path(r"D:\serviceAi")
TARGET = ROOT / "app" / "application" / "services" / "chat_service.py"
BACKUP = TARGET.with_name(
    "chat_service.py.bak_before_active_context_v1"
)

MARKER = "# ACTIVE_CONTEXT_ANALYSIS_V1"

source = TARGET.read_text(encoding="utf-8-sig")

if MARKER in source:
    py_compile.compile(
        str(TARGET),
        doraise=True,
    )
    print("ALREADY_PATCHED")
    print("SOURCE_SYNTAX_OK=True")
    raise SystemExit(0)

old_guard = '''        # FOOD_FINAL_PART1_ORDER_V1
        intent_decision = self.intent_guard.analyze(
            text
        )
'''

new_guard = '''        # ACTIVE_CONTEXT_ANALYSIS_V1
        # When a conversation is waiting for a missing field,
        # analyze the user's reply together with the previous
        # request. Explicit cancellation and explicit new
        # requests must remain independent.
        contextual_analysis_message = message
        contextual_analysis_text = text

        active_nlu_state = (
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

        active_missing_fields = (
            active_nlu_state.get(
                "missingFields"
            )
            if isinstance(
                active_nlu_state.get(
                    "missingFields"
                ),
                list,
            )
            else []
        )

        active_original_message = str(
            conversation_payload.get(
                "originalMessage"
            )
            or ""
        ).strip()

        conversation_cancel_terms = {
            "لغو",
            "لغوش کن",
            "لغو کن",
            "کنسل",
            "کنسل کن",
            "بیخیال",
            "بی خیال",
        }

        if (
            active_missing_fields
            and text in conversation_cancel_terms
        ):
            await self._delete_conversation_state(
                context
            )

            return {
                "reply": (
                    "باشه، درخواست نیمه‌کاره لغو شد."
                ),
                "requiresConfirmation": False,
                "data": {
                    "conversationCancelled": True,
                },
            }

        should_use_active_context = (
            bool(active_missing_fields)
            and bool(active_original_message)
            and text
            not in conversation_cancel_terms
            and not self._looks_like_new_request(
                text
            )
        )

        if should_use_active_context:
            contextual_analysis_message = (
                f"{active_original_message} {text}"
            ).strip()

            contextual_analysis_text = (
                normalize_nlu_text(
                    normalize_persian_text(
                        contextual_analysis_message
                    )
                )
            )

        # FOOD_FINAL_PART1_ORDER_V1
        intent_decision = self.intent_guard.analyze(
            contextual_analysis_text
        )
'''

old_nlu = '''        nlu_result = analyze_message(
            message,
            reference_date=reference_date,
'''

new_nlu = '''        nlu_result = analyze_message(
            contextual_analysis_message,
            reference_date=reference_date,
'''

if source.count(old_guard) != 1:
    raise RuntimeError(
        "GUARD_ANCHOR_NOT_FOUND_OR_DUPLICATED"
    )

if source.count(old_nlu) != 1:
    raise RuntimeError(
        "NLU_ANCHOR_NOT_FOUND_OR_DUPLICATED"
    )

if not BACKUP.exists():
    shutil.copy2(
        TARGET,
        BACKUP,
    )

patched = source.replace(
    old_guard,
    new_guard,
    1,
)

patched = patched.replace(
    old_nlu,
    new_nlu,
    1,
)

TARGET.write_text(
    patched,
    encoding="utf-8",
)

try:
    py_compile.compile(
        str(TARGET),
        doraise=True,
    )
except Exception:
    shutil.copy2(
        BACKUP,
        TARGET,
    )
    py_compile.compile(
        str(TARGET),
        doraise=True,
    )
    print("PATCH_FAILED_ROLLED_BACK")
    raise

sys.path.insert(
    0,
    str(ROOT),
)

from app.application.services.nlu_core import analyze_message

test_state = {
    "domain": "LEAVE",
    "intent": "CREATE_LEAVE",
    "entities": {
        "date": "1405/05/06",
        "startDate": "1405/05/06",
        "endDate": "1405/05/06",
    },
    "missingFields": [
        "requestType",
    ],
}

result = analyze_message(
    "مرخصی ثبت کن برای فردا استحقاقی",
    reference_date="1405/05/05",
    conversation_state=test_state,
)

assert result.get("domain") == "LEAVE"
assert result.get("intent") == "CREATE_LEAVE"

print("PATCH_OK")
print("SOURCE_SYNTAX_OK=True")
print("ACTIVE_CONTEXT_NLU_TEST_OK")
print(f"BACKUP={BACKUP}")