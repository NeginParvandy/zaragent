from __future__ import annotations

from pathlib import Path
import py_compile
import shutil


ROOT = Path(r"D:\serviceAi")

TARGET = ROOT / "probe_get_time_event.py"

BACKUP = TARGET.with_name(
    "probe_get_time_event.py.bak_before_pilot_session"
)

MARKER = "# PROBE_PILOT_SESSION_V1"


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


old_import = """
from app.application.services.hr_service import HrService
from app.core.config import get_settings
from app.domain.models import AgentContext
from app.infrastructure.clients.person.application.services.hr_service import HrService
from app.core.config import get_settings
from app.domain.models import AgentContext
from app.infrastructure.clients.personnel_client import PersonnelClient
""".strip()


new_import = """
from app.api.routes.agent import _apply_pilot_hr_override
from app.application.services.hr_service import HrService
from app.core.config import get_settings
from app.domain.models import AgentContext, UserSession
from app.infrastructure.clients.personnel_client import PersonnelClient
""".strip()


old_context = """
    context = AgentContext(
        employee_id="05000602",
        conversation_id="pilot-05000602",
    )
""".rstrip()


new_context = """
    # PROBE_PILOT_SESSION_V1
    # یک Session خالی ساخته می‌شود تا Override پایلوت
    # دقیقاً با همان منطق Route اصلی روی Context اعمال شود.
    # هیچ Credentialی چاپ یا داخل خروجی Probe ذخیره نمی‌شود.
    context = AgentContext(
        employee_id="05000602",
        conversation_id="pilot-05000602",
        session=UserSession(),
    )

    context = _apply_pilot_hr_override(
        context
    )
""".rstrip()


if source.count(old_import) != 1:
    raise RuntimeError(
        "IMPORT_ANCHOR_NOT_FOUND_OR_DUPLICATED"
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
    old_import,
    new_import,
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

    print("PATCH_FAILED_ROLLED_BACK")
    raise


print("PATCH_OK")
print("SOURCE_SYNTAX_OK=True")
print(f"BACKUP={BACKUP}")