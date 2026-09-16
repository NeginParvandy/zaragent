from __future__ import annotations

from pathlib import Path
import shutil


TARGET = Path(
    r"D:\serviceAi\app\infrastructure\repositories\state_repository.py"
)

BACKUP = Path(
    r"D:\serviceAi\app\infrastructure\repositories"
    r"\state_repository.py.bak_before_unified_chat_step1"
)

METHOD_NAME = "def get_latest_pending_action("

ANCHOR = (
    "    def get_action_state("
    "self, action_id: str, employee_id: str"
    ") -> dict[str, Any] | None:\n"
)

NEW_METHOD = '''    def get_latest_pending_action(
        self,
        employee_id: str,
    ) -> PendingActionRecord | None:
        safe_employee_id = str(
            employee_id or ""
        ).strip()

        if not safe_employee_id:
            return None

        now = _now()
        now_text = _dt_to_text(now)

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")

            conn.execute(
                """
                UPDATE pending_actions
                SET
                    status='expired',
                    updated_at=?
                WHERE
                    employee_id=?
                    AND status='pending'
                    AND expires_at IS NOT NULL
                    AND expires_at<=?
                """,
                (
                    now_text,
                    safe_employee_id,
                    now_text,
                ),
            )

            row = conn.execute(
                """
                SELECT *
                FROM pending_actions
                WHERE
                    employee_id=?
                    AND status='pending'
                    AND (
                        expires_at IS NULL
                        OR expires_at>?
                    )
                ORDER BY
                    created_at DESC,
                    id DESC
                LIMIT 1
                """,
                (
                    safe_employee_id,
                    now_text,
                ),
            ).fetchone()

            conn.commit()

        return (
            self._row_to_action(row)
            if row
            else None
        )

'''

if not TARGET.exists():
    raise FileNotFoundError(
        f"Target file was not found: {TARGET}"
    )

original_text = TARGET.read_text(
    encoding="utf-8-sig"
)

if METHOD_NAME in original_text:
    print(
        "No change was needed: "
        "get_latest_pending_action already exists."
    )
    raise SystemExit(0)

if ANCHOR not in original_text:
    raise RuntimeError(
        "Patch anchor was not found. "
        "No file was changed."
    )

if not BACKUP.exists():
    shutil.copy2(
        TARGET,
        BACKUP,
    )

patched_text = original_text.replace(
    ANCHOR,
    NEW_METHOD + ANCHOR,
    1,
)

compile(
    patched_text,
    str(TARGET),
    "exec",
)

TARGET.write_text(
    patched_text,
    encoding="utf-8",
    newline="\n",
)

print(
    "SUCCESS: get_latest_pending_action "
    "was added safely."
)
print(
    f"Backup: {BACKUP}"
)