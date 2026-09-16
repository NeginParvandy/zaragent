from __future__ import annotations

from pathlib import Path
import py_compile
import shutil


ROOT = Path(r"D:\serviceAi")

TARGET = ROOT / "probe_get_time_event.py"

BACKUP = TARGET.with_name(
    "probe_get_time_event.py.bak_before_pilot_session_v2"
)

MARKER = "# PROBE_PILOT_SESSION_V2"


source = TARGET.read_text(
    encoding="utf-8-sig"
)


if MARKER in source:
    py_compile.compile(
        str(TARGET),
        doraise=True,
    )

    print("ALREADY_PATCHED")
    print("SOURCE_SYNTAX_OK=True")
    raise SystemExit(0)


old_model_import = (
    "from app.domain.models import AgentContext"
)

new_model_import = (
    "from app.domain.models import "
    "AgentContext, UserSession"
)


old_context = '''    context = AgentContext(
        employee_id="05000602",
        conversation_id="pilot-05000602",
    )
'''


new_context = '''    # PROBE_PILOT_SESSION_V2
    # اطلاعات پایلوت فقط در حافظه بارگذاری می‌شوند.
    # هیچ Credentialی چاپ یا داخل فایل خروجی ذخیره نمی‌شود.
    pilot_config_path = (
        ROOT
        / "pilot_hr_override.json"
    )

    pilot_config = json.loads(
        pilot_config_path.read_text(
            encoding="utf-8-sig"
        )
    )

    if pilot_config.get("enabled") is not True:
        raise RuntimeError(
            "PILOT_OVERRIDE_IS_DISABLED"
        )

    pilot_employee_id = str(
        pilot_config.get(
            "employeeId",
            "",
        )
    ).strip()

    pilot_conversation_id = str(
        pilot_config.get(
            "conversationId",
            "pilot-05000602",
        )
        or "pilot-05000602"
    ).strip()

    if pilot_employee_id != "05000602":
        raise RuntimeError(
            "PILOT_EMPLOYEE_ID_MISMATCH"
        )

    if (
        pilot_conversation_id
        != "pilot-05000602"
    ):
        raise RuntimeError(
            "PILOT_CONVERSATION_ID_MISMATCH"
        )

    authorization_token = str(
        pilot_config.get(
            "authorizationToken",
            "",
        )
    ).strip()

    username_hash = str(
        pilot_config.get(
            "usernameHash",
            "",
        )
    ).strip()

    password_hash = str(
        pilot_config.get(
            "passwordHash",
            "",
        )
    ).strip()

    digit_code = pilot_config.get(
        "digitCode"
    )

    if not authorization_token:
        raise RuntimeError(
            "PILOT_AUTH_TOKEN_MISSING"
        )

    if not username_hash:
        raise RuntimeError(
            "PILOT_USERNAME_HASH_MISSING"
        )

    if not password_hash:
        raise RuntimeError(
            "PILOT_PASSWORD_HASH_MISSING"
        )

    if digit_code is None:
        raise RuntimeError(
            "PILOT_DIGIT_CODE_MISSING"
        )

    session = UserSession(
        authorization_token=authorization_token,
        username_hash=username_hash,
        password_hash=password_hash,
        digit_code=int(digit_code),
    )

    context = AgentContext(
        employee_id=pilot_employee_id,
        conversation_id=pilot_conversation_id,
        session=session,
    )
'''


if source.count(old_model_import) != 1:
    raise RuntimeError(
        "MODEL_IMPORT_ANCHOR_NOT_FOUND_OR_DUPLICATED"
    )


if source.count(old_context) != 1:
    raise RuntimeError(
        "CONTEXT_ANCHOR_NOT_FOUND_OR_DUPLICATED"
    )


if not BACKUP.exists():
    shutil.copy2(
        TARGET,
        BACKUP,
    )


patched = source.replace(
    old_model_import,
    new_model_import,
    1,
)

patched = patched.replace(
    old_context,
    new_context,
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

    print(
        "PATCH_FAILED_ROLLED_BACK"
    )
    raise


print("PATCH_OK")
print("SOURCE_SYNTAX_OK=True")
print(f"BACKUP={BACKUP}")