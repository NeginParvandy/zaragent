from __future__ import annotations

import py_compile
import re
import sys
from pathlib import Path
from shutil import copy2


ROOT_DIR = Path(r"D:\serviceAi")

TARGET_FILE = ROOT_DIR / "app" / "domain" / "models.py"

HEALTHY_BACKUP_FILE = TARGET_FILE.with_name(
    "models.py.bak_before_remove_chat_date"
)

BROKEN_BACKUP_FILE = TARGET_FILE.with_name(
    "models.py.bak_broken_after_remove_chat_date"
)

MARKER = "# PUBLIC_CHAT_DATE_REMOVED_SAFE"


def fail(message: str) -> None:
    print(f"FAILED: {message}")
    sys.exit(1)


def main() -> None:
    if not TARGET_FILE.exists():
        fail(f"Target file not found: {TARGET_FILE}")

    if not HEALTHY_BACKUP_FILE.exists():
        fail(
            "Healthy backup was not found: "
            f"{HEALTHY_BACKUP_FILE}"
        )

    current_text = TARGET_FILE.read_text(
        encoding="utf-8"
    )

    healthy_text = HEALTHY_BACKUP_FILE.read_text(
        encoding="utf-8"
    )

    required_classes = (
        "class ChatContextRequest",
        "class DailyBriefRequest",
        "class ChatRequest",
    )

    for required_class in required_classes:
        if required_class not in healthy_text:
            fail(
                f"Healthy backup is missing: {required_class}"
            )

    pattern = re.compile(
        r"class ChatContextRequest"
        r"\(EmployeeRequestBase\):\r?\n"
        r".*?"
        r"(?=\r?\nclass DailyBriefRequest\()",
        re.DOTALL,
    )

    matches = pattern.findall(healthy_text)

    if len(matches) != 1:
        fail(
            "Expected exactly one ChatContextRequest block, "
            f"but found {len(matches)}."
        )

    new_chat_context = '''class ChatContextRequest(EmployeeRequestBase):
    """Public context accepted by the Chat API."""

    # PUBLIC_CHAT_DATE_REMOVED_SAFE
    session: UserSession | None = Field(
        default=None
    )

    def to_context(self) -> AgentContext:
        return AgentContext(
            employee_id=self.employee_id,
            session=self.session,
        )
'''

    repaired_text, replacement_count = pattern.subn(
        new_chat_context,
        healthy_text,
        count=1,
    )

    if replacement_count != 1:
        fail("ChatContextRequest replacement failed.")

    copy2(
        TARGET_FILE,
        BROKEN_BACKUP_FILE,
    )

    try:
        TARGET_FILE.write_text(
            repaired_text,
            encoding="utf-8",
        )

        py_compile.compile(
            str(TARGET_FILE),
            doraise=True,
        )

        sys.path.insert(
            0,
            str(ROOT_DIR),
        )

        from app.domain.models import (
            AgentContext,
            ChatRequest,
            DailyBriefRequest,
        )

        schema = ChatRequest.model_json_schema()

        context_properties = (
            schema
            .get("$defs", {})
            .get("ChatContextRequest", {})
            .get("properties", {})
        )

        property_names = list(
            context_properties.keys()
        )

        if property_names != [
            "employeeId",
            "session",
        ]:
            raise RuntimeError(
                "Unexpected public Chat fields: "
                f"{property_names}"
            )

        agent_fields = AgentContext.model_fields

        if "date" not in agent_fields:
            raise RuntimeError(
                "Internal AgentContext.date was removed."
            )

        if DailyBriefRequest is None:
            raise RuntimeError(
                "DailyBriefRequest import failed."
            )

    except Exception as exc:
        TARGET_FILE.write_text(
            current_text,
            encoding="utf-8",
        )

        fail(
            "Repair was rolled back because "
            f"validation failed: {exc}"
        )

    print("SUCCESS")
    print(f"Repaired: {TARGET_FILE}")
    print(f"Healthy source: {HEALTHY_BACKUP_FILE}")
    print(f"Broken copy saved: {BROKEN_BACKUP_FILE}")
    print(
        "Public Chat fields: employeeId, session"
    )
    print(
        "DailyBriefRequest and internal AgentContext.date "
        "were preserved."
    )


if __name__ == "__main__":
    main()