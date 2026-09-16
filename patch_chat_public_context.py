from __future__ import annotations

from pathlib import Path
import re
import shutil


TARGET = Path(
    r"D:\serviceAi\app\domain\models.py"
)

BACKUP = Path(
    r"D:\serviceAi\app\domain"
    r"\models.py.bak_before_chat_public_context"
)

NEW_CLASS = '''class ChatContextRequest(EmployeeRequestBase):
    """
    Context عمومی مخصوص POST /api/agent/chat.

    restaurantId و mealId در قرارداد عمومی Chat
    وجود ندارند و داخل Agent تعیین می‌شوند.
    """

    date: str | None = None
    session: UserSession | None = None

    @field_validator("date")
    @classmethod
    def validate_date(
        cls,
        value: str | None,
    ) -> str | None:
        if not value:
            return None

        return normalize_jalali_date(value)

    def to_context(
        self,
        **overrides: Any,
    ) -> AgentContext:
        data: dict[str, Any] = {
            "employee_id": self.employee_id,
            "date": self.date,
            "session": self.session,
        }

        data.update(overrides)

        return AgentContext(**data)


'''

if not TARGET.exists():
    raise FileNotFoundError(
        f"Target file was not found: {TARGET}"
    )

original_text = TARGET.read_text(
    encoding="utf-8-sig"
)

if (
    "class ChatContextRequest(EmployeeRequestBase):"
    in original_text
):
    print(
        "No change was needed: Chat public context "
        "is already clean."
    )
    raise SystemExit(0)

pattern = re.compile(
    r"^class ChatContextRequest"
    r"\(IntegrationContextRequest\):"
    r".*?(?=^class\s+\w+)",
    flags=re.MULTILINE | re.DOTALL,
)

match = pattern.search(original_text)

if match is None:
    raise RuntimeError(
        "ChatContextRequest class was not found. "
        "No file was changed."
    )

patched_text = (
    original_text[:match.start()]
    + NEW_CLASS
    + original_text[match.end():]
)

compile(
    patched_text,
    str(TARGET),
    "exec",
)

if not BACKUP.exists():
    shutil.copy2(
        TARGET,
        BACKUP,
    )

TARGET.write_text(
    patched_text,
    encoding="utf-8",
    newline="\n",
)

print(
    "SUCCESS: restaurantId and mealId were removed "
    "from the public Chat context."
)
print(
    f"Backup: {BACKUP}"
)