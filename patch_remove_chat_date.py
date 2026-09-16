from __future__ import annotations

import py_compile
import re
import sys
from pathlib import Path
from shutil import copy2


ROOT_DIR = Path(r"D:\serviceAi")

TARGET_FILE = (
    ROOT_DIR
    / "app"
    / "domain"
    / "models.py"
)

BACKUP_FILE = TARGET_FILE.with_name(
    "models.py.bak_before_remove_chat_date"
)

MARKER = "# PUBLIC_CHAT_DATE_REMOVED"


def fail(message: str) -> None:
    print(f"FAILED: {message}")
    sys.exit(1)


def restore_backup() -> None:
    if BACKUP_FILE.exists():
        copy2(BACKUP_FILE, TARGET_FILE)


def main() -> None:
    if not TARGET_FILE.exists():
        fail(f"Target file not found: {TARGET_FILE}")

    original_text = TARGET_FILE.read_text(
        encoding="utf-8"
    )

    pattern = re.compile(
        r"class ChatContextRequest"
        r"\(EmployeeRequestBase\):\r?\n"
        r".*?"
        r"(?=\r?\nclass ChatRequest\()",
        re.DOTALL,
    )

    match = pattern.search(original_text)

    if not match:
        fail(
            "ChatContextRequest class was not found."
        )

    current_block = match.group(0)

    if (
        MARKER in current_block
        and not re.search(
            r"^\s+date\s*:",
            current_block,
            re.MULTILINE,
        )
    ):
        print(
            "SKIPPED: date is already removed "
            "from ChatContextRequest."
        )
        return

    new_block = '''class ChatContextRequest(EmployeeRequestBase):
    """Public context accepted by the Chat API."""

    # PUBLIC_CHAT_DATE_REMOVED
    session: UserSession | None = Field(
        default=None
    )

    def to_context(self) -> AgentContext:
        return AgentContext(
            employee_id=self.employee_id,
            session=self.session,
        )
'''

    updated_text, replacement_count = (
        pattern.subn(
            new_block,
            original_text,
            count=1,
        )
    )

    if replacement_count != 1:
        fail(
            "ChatContextRequest replacement failed."
        )

    copy2(
        TARGET_FILE,
        BACKUP_FILE,
    )

    try:
        TARGET_FILE.write_text(
            updated_text,
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

        from app.domain.models import ChatRequest

        schema = ChatRequest.model_json_schema()

        context_schema = (
            schema
            .get("$defs", {})
            .get("ChatContextRequest", {})
        )

        properties = context_schema.get(
            "properties",
            {},
        )

        property_names = list(
            properties.keys()
        )

        if "date" in property_names:
            raise RuntimeError(
                "date still exists in ChatContextRequest."
            )

        if "employeeId" not in property_names:
            raise RuntimeError(
                "employeeId is missing from "
                "ChatContextRequest."
            )

        if "session" not in property_names:
            raise RuntimeError(
                "session is missing from "
                "ChatContextRequest."
            )

    except Exception as exc:
        restore_backup()

        fail(
            "Patch was rolled back because "
            f"validation failed: {exc}"
        )

    print("SUCCESS")
    print(f"Patched: {TARGET_FILE}")
    print(f"Backup: {BACKUP_FILE}")
    print(
        "Public Chat fields: "
        "employeeId, session"
    )
    print(
        "Internal AgentContext.date was preserved."
    )


if __name__ == "__main__":
    main()