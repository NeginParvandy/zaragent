from pathlib import Path
import shutil


TARGET = Path(
    r"D:\serviceAi\app\api\routes\agent.py"
)

BACKUP = Path(
    r"D:\serviceAi\app\api\routes"
    r"\agent.py.bak_before_pilot_override_scope"
)

TEMP = Path(
    r"D:\serviceAi\app\api\routes"
    r"\agent.py.pilot_override_scope.tmp"
)

MARKER = "PILOT_HR_OVERRIDE_SCOPE_V1"


text = TARGET.read_text(
    encoding="utf-8-sig"
)

if MARKER in text:
    print("ALREADY_PATCHED")
    raise SystemExit(0)


old = '''    if (
        not configured_employee_id
        or configured_employee_id
        != current_employee_id
    ):
        return context

    authorization_token = str(
'''


new = '''    if (
        not configured_employee_id
        or configured_employee_id
        != current_employee_id
    ):
        return context

    # PILOT_HR_OVERRIDE_SCOPE_V1
    # Only the legacy .NET pilot bridge uses the fixed
    # credentials stored in pilot_hr_override.json.
    # Direct Swagger calls keep the session sent in Request.
    conversation_id = str(
        context.conversation_id or ""
    ).strip()

    if conversation_id != "pilot-05000602":
        logger.info(
            (
                "PILOT_HR_OVERRIDE_SKIPPED "
                "employee_id=%s "
                "reason=non_bridge_conversation"
            ),
            current_employee_id,
        )
        return context

    authorization_token = str(
'''


count = text.count(old)

if count != 1:
    raise RuntimeError(
        "PILOT_OVERRIDE_SCOPE: "
        f"expected 1 match, found {count}"
    )

updated = text.replace(
    old,
    new,
    1,
)

compile(
    updated,
    str(TARGET),
    "exec",
)

if not BACKUP.exists():
    shutil.copy2(
        TARGET,
        BACKUP,
    )

TEMP.write_text(
    updated,
    encoding="utf-8",
)

TEMP.replace(TARGET)

print("PATCH_OK")
print(f"BACKUP={BACKUP}")