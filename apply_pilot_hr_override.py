from pathlib import Path
from dataclasses import is_dataclass, replace
import json
import py_compile
import shutil


TARGET = Path(r"D:\serviceAi\app\api\routes\agent.py")
OVERRIDE_FILE = Path(r"D:\serviceAi\pilot_hr_override.json")
BACKUP = Path(
    r"D:\serviceAi\app\api\routes\agent.py.bak_before_pilot_hr_override"
)


def validate_override_file() -> None:
    if not OVERRIDE_FILE.exists():
        raise FileNotFoundError(
            f"Override file not found: {OVERRIDE_FILE}"
        )

    data = json.loads(
        OVERRIDE_FILE.read_text(encoding="utf-8")
    )

    required = (
        "enabled",
        "employeeId",
        "authorizationToken",
        "usernameHash",
        "passwordHash",
        "digitCode",
    )

    missing = [
        key
        for key in required
        if key not in data
    ]

    if missing:
        raise RuntimeError(
            "Missing override fields: "
            + ", ".join(missing)
        )

    if not isinstance(data["enabled"], bool):
        raise RuntimeError(
            "enabled must be true or false."
        )

    if not str(data["employeeId"]).strip():
        raise RuntimeError(
            "employeeId is empty."
        )

    for key in (
        "authorizationToken",
        "usernameHash",
        "passwordHash",
    ):
        if not str(data[key]).strip():
            raise RuntimeError(
                f"{key} is empty."
            )

    try:
        int(data["digitCode"])
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            "digitCode must be numeric."
        ) from exc


if not TARGET.exists():
    raise FileNotFoundError(
        f"Target file not found: {TARGET}"
    )

validate_override_file()

text = TARGET.read_text(
    encoding="utf-8"
)

if "PILOT_HR_OVERRIDE_APPLIED" in text:
    print("OVERRIDE_ALREADY_INSTALLED=True")
    raise SystemExit(0)


if "import json\n" not in text:
    marker = "import hashlib\n"

    if marker not in text:
        raise RuntimeError(
            "Import marker not found. No file changed."
        )

    text = text.replace(
        marker,
        marker + "import json\n",
        1,
    )


if "from pathlib import Path\n" not in text:
    import_marker = "import logging\n"

    if import_marker not in text:
        raise RuntimeError(
            "Logging import marker not found. "
            "No file changed."
        )

    text = text.replace(
        import_marker,
        import_marker + "from pathlib import Path\n",
        1,
    )


if (
    "from dataclasses import is_dataclass, replace\n"
    not in text
):
    import_marker = "from pathlib import Path\n"

    text = text.replace(
        import_marker,
        import_marker
        + "from dataclasses import is_dataclass, replace\n",
        1,
    )


helper_marker = (
    "logger = logging.getLogger(__name__)\n\n"
    "router = APIRouter("
)

helper_block = r'''logger = logging.getLogger(__name__)


_PILOT_HR_OVERRIDE_PATH = Path(
    r"D:\serviceAi\pilot_hr_override.json"
)


def _copy_with_update(value, changes):
    model_copy = getattr(
        value,
        "model_copy",
        None,
    )

    if callable(model_copy):
        return model_copy(
            update=changes
        )

    copy_method = getattr(
        value,
        "copy",
        None,
    )

    if callable(copy_method):
        try:
            return copy_method(
                update=changes
            )
        except TypeError:
            pass

    if is_dataclass(value):
        return replace(
            value,
            **changes,
        )

    for key, item in changes.items():
        setattr(
            value,
            key,
            item,
        )

    return value


def _apply_pilot_hr_override(context):
    try:
        config = json.loads(
            _PILOT_HR_OVERRIDE_PATH.read_text(
                encoding="utf-8"
            )
        )
    except FileNotFoundError:
        return context
    except Exception:
        logger.exception(
            "PILOT_HR_OVERRIDE_INVALID_FILE"
        )
        return context

    if config.get("enabled") is not True:
        return context

    configured_employee_id = str(
        config.get(
            "employeeId",
            "",
        )
    ).strip()

    current_employee_id = str(
        context.employee_id or ""
    ).strip()

    if (
        not configured_employee_id
        or configured_employee_id
        != current_employee_id
    ):
        return context

    authorization_token = str(
        config.get(
            "authorizationToken",
            "",
        )
    ).strip()

    username_hash = str(
        config.get(
            "usernameHash",
            "",
        )
    ).strip()

    password_hash = str(
        config.get(
            "passwordHash",
            "",
        )
    ).strip()

    digit_code = config.get(
        "digitCode"
    )

    if not all(
        (
            authorization_token,
            username_hash,
            password_hash,
            digit_code is not None,
        )
    ):
        logger.error(
            (
                "PILOT_HR_OVERRIDE_SKIPPED "
                "employee_id=%s reason=incomplete_config"
            ),
            current_employee_id,
        )
        return context

    session = context.session

    if session is None:
        logger.error(
            (
                "PILOT_HR_OVERRIDE_SKIPPED "
                "employee_id=%s reason=no_session"
            ),
            current_employee_id,
        )
        return context

    updated_session = _copy_with_update(
        session,
        {
            "authorization_token": authorization_token,
            "username_hash": username_hash,
            "password_hash": password_hash,
            "digit_code": int(digit_code),
        },
    )

    updated_context = _copy_with_update(
        context,
        {
            "session": updated_session,
        },
    )

    logger.warning(
        (
            "PILOT_HR_OVERRIDE_APPLIED "
            "employee_id=%s"
        ),
        current_employee_id,
    )

    return updated_context


router = APIRouter('''

if helper_marker not in text:
    raise RuntimeError(
        "Logger/router marker not found. "
        "No file changed."
    )

text = text.replace(
    helper_marker,
    helper_block,
    1,
)


call_marker = '''    session = context.session

    logger.info(
'''

call_replacement = '''    context = _apply_pilot_hr_override(
        context
    )

    session = context.session

    logger.info(
'''

if call_marker not in text:
    raise RuntimeError(
        "Trace/session marker not found. "
        "No file changed."
    )

text = text.replace(
    call_marker,
    call_replacement,
    1,
)


candidate = Path(
    r"D:\serviceAi\agent_pilot_override_candidate.py"
)

candidate.write_text(
    text,
    encoding="utf-8",
)

py_compile.compile(
    str(candidate),
    doraise=True,
)

shutil.copy2(
    TARGET,
    BACKUP,
)

shutil.copy2(
    candidate,
    TARGET,
)

py_compile.compile(
    str(TARGET),
    doraise=True,
)

candidate.unlink(
    missing_ok=True
)

print(f"BACKUP_OK={BACKUP}")
print(f"UPDATED_OK={TARGET}")
print("OVERRIDE_CONFIG_OK=True")
print("COMPILE_OK=True")