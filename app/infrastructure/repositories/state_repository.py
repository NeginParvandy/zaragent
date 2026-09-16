from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.domain.models import PendingActionRecord, ReminderRecord

SCHEMA_VERSION = 6
DEFAULT_CONVERSATION_ID = "__default__"


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _dt_to_text(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _dt_from_text(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class StateRepository:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.path: Path = settings.sqlite_file
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.path,
            timeout=self.settings.sqlite_busy_timeout_ms / 1000,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(f"PRAGMA busy_timeout={self.settings.sqlite_busy_timeout_ms}")
        return conn

    @staticmethod
    def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
        return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}

    @staticmethod
    def _table_exists(
        conn: sqlite3.Connection,
        table: str,
    ) -> bool:
        row = conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type='table' AND name=?
            LIMIT 1
            """,
            (str(table),),
        ).fetchone()
        return row is not None

    @staticmethod
    def _normalize_conversation_id(
        conversation_id: str | None,
    ) -> str:
        value = str(
            conversation_id or ""
        ).strip()
        return value or DEFAULT_CONVERSATION_ID

    def _migrate_chat_states_schema(
        self,
        conn: sqlite3.Connection,
    ) -> None:
        if not self._table_exists(
            conn,
            "chat_states",
        ):
            conn.execute(
                """
                CREATE TABLE chat_states (
                    employee_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    state_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    PRIMARY KEY(
                        employee_id,
                        conversation_id
                    )
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS
                idx_chat_states_expires_at
                ON chat_states(expires_at)
                """
            )
            return

        table_info = conn.execute(
            "PRAGMA table_info(chat_states)"
        ).fetchall()

        columns = {
            str(row["name"])
            for row in table_info
        }

        primary_key_columns = [
            str(row["name"])
            for row in sorted(
                table_info,
                key=lambda item: int(
                    item["pk"] or 0
                ),
            )
            if int(row["pk"] or 0) > 0
        ]

        expected_primary_key = [
            "employee_id",
            "conversation_id",
        ]

        if (
            "conversation_id" in columns
            and primary_key_columns
            == expected_primary_key
        ):
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS
                idx_chat_states_expires_at
                ON chat_states(expires_at)
                """
            )
            return

        legacy_table = (
            "chat_states_legacy_v5"
        )

        conn.execute(
            """
            DROP INDEX IF EXISTS
            idx_chat_states_expires_at
            """
        )

        if self._table_exists(
            conn,
            legacy_table,
        ):
            conn.execute(
                f"DROP TABLE {legacy_table}"
            )

        conn.execute(
            f"""
            ALTER TABLE chat_states
            RENAME TO {legacy_table}
            """
        )

        conn.execute(
            """
            CREATE TABLE chat_states (
                employee_id TEXT NOT NULL,
                conversation_id TEXT NOT NULL,
                state_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                PRIMARY KEY(
                    employee_id,
                    conversation_id
                )
            )
            """
        )

        legacy_columns = self._columns(
            conn,
            legacy_table,
        )

        if "conversation_id" in legacy_columns:
            conversation_expression = (
                "COALESCE("
                "NULLIF(TRIM(conversation_id), ''), "
                f"'{DEFAULT_CONVERSATION_ID}'"
                ")"
            )
        else:
            conversation_expression = (
                f"'{DEFAULT_CONVERSATION_ID}'"
            )

        conn.execute(
            f"""
            INSERT OR REPLACE INTO chat_states(
                employee_id,
                conversation_id,
                state_type,
                payload,
                created_at,
                expires_at
            )
            SELECT
                employee_id,
                {conversation_expression},
                state_type,
                payload,
                created_at,
                expires_at
            FROM {legacy_table}
            """
        )

        conn.execute(
            f"DROP TABLE {legacy_table}"
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_chat_states_expires_at
            ON chat_states(expires_at)
            """
        )

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS pending_actions (
                    id TEXT PRIMARY KEY,
                    employee_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT,
                    result TEXT,
                    error_message TEXT,
                    idempotency_key TEXT NOT NULL,
                    dedup_key TEXT,
                    reminder_id TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_pending_actions_employee_status ON pending_actions(employee_id, status);

                CREATE TABLE IF NOT EXISTS reminders (
                    id TEXT PRIMARY KEY,
                    employee_id TEXT NOT NULL,
                    module TEXT NOT NULL,
                    reminder_type TEXT NOT NULL,
                    target_date TEXT,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    actions TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    shown_at TEXT,
                    acted_at TEXT,
                    data TEXT NOT NULL,
                    dedup_key TEXT NOT NULL,
                    action_id TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_reminders_employee_status ON reminders(employee_id, status);
                CREATE INDEX IF NOT EXISTS idx_reminders_dedup_created ON reminders(employee_id, dedup_key, created_at);

                CREATE TABLE IF NOT EXISTS chat_states (
                    employee_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    state_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    PRIMARY KEY(
                        employee_id,
                        conversation_id
                    )
                );
                CREATE INDEX IF NOT EXISTS idx_chat_states_expires_at ON chat_states(expires_at);

                CREATE TABLE IF NOT EXISTS daily_reminder_deliveries (
                    employee_id TEXT NOT NULL,
                    target_date TEXT NOT NULL,
                    delivered_at TEXT NOT NULL,
                    reminder_count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(employee_id, target_date)
                );
                CREATE INDEX IF NOT EXISTS idx_daily_reminder_deliveries_date
                ON daily_reminder_deliveries(target_date);
                """
            )
            pending_columns = self._columns(conn, "pending_actions")
            pending_additions = {
                "updated_at": "TEXT NOT NULL DEFAULT ''",
                "idempotency_key": "TEXT NOT NULL DEFAULT ''",
                "dedup_key": "TEXT",
                "reminder_id": "TEXT",
            }
            for name, definition in pending_additions.items():
                if name not in pending_columns:
                    conn.execute(f"ALTER TABLE pending_actions ADD COLUMN {name} {definition}")
            reminder_columns = self._columns(conn, "reminders")
            if "action_id" not in reminder_columns:
                conn.execute("ALTER TABLE reminders ADD COLUMN action_id TEXT")
            conn.execute("UPDATE pending_actions SET updated_at=created_at WHERE updated_at IS NULL OR updated_at='' ")
            conn.execute("UPDATE pending_actions SET idempotency_key=id WHERE idempotency_key IS NULL OR idempotency_key='' ")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pending_actions_dedup ON pending_actions(employee_id, dedup_key, status)")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_pending_actions_idempotency ON pending_actions(idempotency_key)")
            self._migrate_chat_states_schema(conn)
            conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            conn.commit()

    def health_check(self) -> dict[str, Any]:
        with self._connect() as conn:
            quick_check = conn.execute("PRAGMA quick_check").fetchone()[0]
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("SELECT 1")
            conn.rollback()
        return {"database": "ok" if quick_check == "ok" else str(quick_check), "schemaVersion": SCHEMA_VERSION, "writable": True}

    def save_pending_action(self, record: PendingActionRecord, dedup_key: str | None = None) -> PendingActionRecord:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if dedup_key:
                row = conn.execute(
                    "SELECT * FROM pending_actions "
                    "WHERE employee_id=? AND dedup_key=? "
                    "AND status IN ('pending','processing') "
                    "AND (expires_at IS NULL OR expires_at>?) "
                    "ORDER BY created_at DESC LIMIT 1",
                    (record.employee_id, dedup_key, _dt_to_text(_now())),
                ).fetchone()
                if row:
                    conn.commit()
                    return self._row_to_action(row)
            self._insert_action(conn, record, dedup_key=dedup_key)
            conn.commit()
            return record

    def _insert_action(self, conn: sqlite3.Connection, record: PendingActionRecord, *, dedup_key: str | None = None) -> None:
        conn.execute(
            """
            INSERT INTO pending_actions(
                id, employee_id, action_type, payload, status, created_at, updated_at, expires_at,
                result, error_message, idempotency_key, dedup_key, reminder_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?)
            """,
            (
                record.id,
                record.employee_id,
                record.action_type,
                json.dumps(record.payload, ensure_ascii=False, sort_keys=True),
                record.status,
                _dt_to_text(record.created_at),
                _dt_to_text(record.updated_at),
                _dt_to_text(record.expires_at),
                record.idempotency_key,
                dedup_key,
                record.reminder_id,
            ),
        )

    def get_pending_action(self, action_id: str, employee_id: str | None = None) -> PendingActionRecord | None:
        sql = "SELECT * FROM pending_actions WHERE id=?"
        params: list[Any] = [action_id]
        if employee_id:
            sql += " AND employee_id=?"
            params.append(employee_id)
        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return self._row_to_action(row) if row else None

    def get_latest_pending_action(
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

    def get_action_state(self, action_id: str, employee_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, employee_id, action_type, status, created_at, updated_at, expires_at, result, error_message "
                "FROM pending_actions WHERE id=? AND employee_id=?",
                (action_id, employee_id),
            ).fetchone()
        if not row:
            return None
        result: Any = None
        if row["result"]:
            try:
                result = json.loads(row["result"])
            except (TypeError, json.JSONDecodeError):
                result = None
        return {
            "actionId": row["id"],
            "actionType": row["action_type"],
            "status": row["status"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "expiresAt": row["expires_at"],
            "result": result,
            "error": row["error_message"],
        }

    def claim_pending_action(self, action_id: str, employee_id: str) -> PendingActionRecord | None:
        now = _now()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM pending_actions WHERE id=? AND employee_id=?", (action_id, employee_id)).fetchone()
            if not row:
                conn.rollback()
                return None
            record = self._row_to_action(row)
            if record.status != "pending":
                conn.rollback()
                return None
            if record.expires_at and record.expires_at <= now:
                conn.execute(
                    "UPDATE pending_actions SET status='expired', updated_at=? WHERE id=? AND status='pending'",
                    (_dt_to_text(now), action_id),
                )
                conn.commit()
                return None
            changed = conn.execute(
                "UPDATE pending_actions SET status='processing', updated_at=? WHERE id=? AND employee_id=? AND status='pending'",
                (_dt_to_text(now), action_id, employee_id),
            )
            if changed.rowcount != 1:
                conn.rollback()
                return None
            conn.commit()
            return record.model_copy(update={"status": "processing", "updated_at": now})

    def complete_pending_action(self, action_id: str, status: str, *, result: Any = None, error_message: str | None = None) -> bool:
        if status not in {"succeeded", "failed", "unknown"}:
            raise ValueError("invalid final action status")
        now = _now()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT reminder_id FROM pending_actions WHERE id=? AND status=?", (action_id, "processing")).fetchone()
            if not row:
                conn.rollback()
                return False
            conn.execute(
                "UPDATE pending_actions SET status=?, result=?, error_message=?, updated_at=? WHERE id=? AND status=?",
                (
                    status,
                    json.dumps(result, ensure_ascii=False) if result is not None else None,
                    error_message,
                    _dt_to_text(now),
                    action_id,
                    "processing",
                ),
            )
            reminder_id = row["reminder_id"]
            if reminder_id and status == "succeeded":
                conn.execute(
                    "UPDATE reminders SET status='acted', acted_at=? WHERE id=? AND status IN ('pending','shown')",
                    (_dt_to_text(now), reminder_id),
                )
            conn.commit()
            return True

    def cancel_pending_action(self, action_id: str, employee_id: str) -> bool:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT reminder_id FROM pending_actions WHERE id=? AND employee_id=? AND status=?", (action_id, employee_id, "pending")
            ).fetchone()
            if not row:
                conn.rollback()
                return False
            conn.execute(
                "UPDATE pending_actions SET status='cancelled', updated_at=? WHERE id=? AND status='pending'",
                (_dt_to_text(_now()), action_id),
            )
            if row["reminder_id"]:
                conn.execute(
                    "UPDATE reminders SET status='dismissed', shown_at=COALESCE(shown_at, ?) WHERE id=? AND status IN ('pending','shown')",
                    (_dt_to_text(_now()), row["reminder_id"]),
                )
            conn.commit()
            return True

    def save_chat_state(
        self,
        employee_id: str,
        state_type: str,
        payload: dict[str, Any],
        ttl_minutes: int = 10,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        safe_employee_id = str(
            employee_id
        ).strip()

        safe_conversation_id = (
            self._normalize_conversation_id(
                conversation_id
            )
        )

        safe_state_type = str(
            state_type
        ).strip()

        if not safe_employee_id:
            raise ValueError(
                "employee_id is required"
            )

        if not safe_state_type:
            raise ValueError(
                "state_type is required"
            )

        now = _now()
        expires_at = now + timedelta(
            minutes=max(
                1,
                int(ttl_minutes),
            )
        )
        safe_payload = payload or {}

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                INSERT INTO chat_states(
                    employee_id,
                    conversation_id,
                    state_type,
                    payload,
                    created_at,
                    expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(
                    employee_id,
                    conversation_id
                ) DO UPDATE SET
                    state_type=excluded.state_type,
                    payload=excluded.payload,
                    created_at=excluded.created_at,
                    expires_at=excluded.expires_at
                """,
                (
                    safe_employee_id,
                    safe_conversation_id,
                    safe_state_type,
                    json.dumps(
                        safe_payload,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    _dt_to_text(now),
                    _dt_to_text(expires_at),
                ),
            )
            conn.commit()

        return {
            "employeeId": safe_employee_id,
            "conversationId": (
                safe_conversation_id
            ),
            "stateType": safe_state_type,
            "payload": safe_payload,
            "createdAt": _dt_to_text(now),
            "expiresAt": _dt_to_text(
                expires_at
            ),
        }

    def get_chat_state(
        self,
        employee_id: str,
        conversation_id: str | None = None,
    ) -> dict[str, Any] | None:
        safe_employee_id = str(
            employee_id
        ).strip()

        if not safe_employee_id:
            return None

        safe_conversation_id = (
            self._normalize_conversation_id(
                conversation_id
            )
        )

        now = _now()

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    employee_id,
                    conversation_id,
                    state_type,
                    payload,
                    created_at,
                    expires_at
                FROM chat_states
                WHERE
                    employee_id=?
                    AND conversation_id=?
                """,
                (
                    safe_employee_id,
                    safe_conversation_id,
                ),
            ).fetchone()

            if not row:
                return None

            expires_at = _dt_from_text(
                row["expires_at"]
            )

            if (
                expires_at is None
                or expires_at <= now
            ):
                conn.execute(
                    """
                    DELETE FROM chat_states
                    WHERE
                        employee_id=?
                        AND conversation_id=?
                    """,
                    (
                        safe_employee_id,
                        safe_conversation_id,
                    ),
                )
                conn.commit()
                return None

            payload = self._json_load(
                row["payload"],
                {},
            )

            if not isinstance(
                payload,
                dict,
            ):
                payload = {}

            return {
                "employeeId": row[
                    "employee_id"
                ],
                "conversationId": row[
                    "conversation_id"
                ],
                "stateType": row[
                    "state_type"
                ],
                "payload": payload,
                "createdAt": row[
                    "created_at"
                ],
                "expiresAt": row[
                    "expires_at"
                ],
            }

    def delete_chat_state(
        self,
        employee_id: str,
        conversation_id: str | None = None,
    ) -> bool:
        safe_employee_id = str(
            employee_id
        ).strip()

        if not safe_employee_id:
            return False

        safe_conversation_id = (
            self._normalize_conversation_id(
                conversation_id
            )
        )

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            result = conn.execute(
                """
                DELETE FROM chat_states
                WHERE
                    employee_id=?
                    AND conversation_id=?
                """,
                (
                    safe_employee_id,
                    safe_conversation_id,
                ),
            )
            conn.commit()

        return result.rowcount > 0


    def has_daily_reminder_delivery(
        self,
        employee_id: str,
        target_date: str,
    ) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM daily_reminder_deliveries
                WHERE employee_id=? AND target_date=?
                LIMIT 1
                """,
                (
                    str(employee_id),
                    str(target_date),
                ),
            ).fetchone()

        return row is not None

    def claim_daily_reminder_delivery(
        self,
        employee_id: str,
        target_date: str,
        reminder_count: int,
    ) -> bool:
        now_text = _dt_to_text(_now())

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")

            result = conn.execute(
                """
                INSERT OR IGNORE INTO daily_reminder_deliveries(
                    employee_id,
                    target_date,
                    delivered_at,
                    reminder_count
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    str(employee_id),
                    str(target_date),
                    now_text,
                    max(0, int(reminder_count)),
                ),
            )

            if result.rowcount != 1:
                conn.commit()
                return False

            conn.execute(
                """
                UPDATE reminders
                SET
                    status='shown',
                    shown_at=COALESCE(shown_at, ?)
                WHERE
                    employee_id=?
                    AND target_date=?
                    AND status='pending'
                """,
                (
                    now_text,
                    str(employee_id),
                    str(target_date),
                ),
            )

            conn.commit()
            return True

    def list_reminders_for_date(
        self,
        employee_id: str,
        target_date: str,
    ) -> list[ReminderRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM reminders
                WHERE
                    employee_id=?
                    AND target_date=?
                    AND status IN ('pending', 'shown')
                ORDER BY created_at ASC
                """,
                (
                    str(employee_id),
                    str(target_date),
                ),
            ).fetchall()

        return [
            self._row_to_reminder(row)
            for row in rows
        ]

    def save_reminder(self, record: ReminderRecord, dedup_hours: int) -> bool:
        return self._save_reminder_internal(record, dedup_hours, action=None)

    def save_reminder_with_action(self, record: ReminderRecord, action: PendingActionRecord, dedup_hours: int) -> bool:
        return self._save_reminder_internal(record, dedup_hours, action=action)

    def _save_reminder_internal(self, record: ReminderRecord, dedup_hours: int, action: PendingActionRecord | None) -> bool:
        dedup_key = self._dedup_key(record)
        cutoff = _now() - timedelta(hours=dedup_hours)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT id FROM reminders WHERE employee_id=? AND dedup_key=? AND created_at>=? LIMIT 1",
                (record.employee_id, dedup_key, _dt_to_text(cutoff)),
            ).fetchone()
            if existing:
                conn.rollback()
                return False
            if action:
                self._insert_action(conn, action, dedup_key=f"reminder:{dedup_key}")
            conn.execute(
                """
                INSERT INTO reminders(
                    id, employee_id, module, reminder_type, target_date, title, message, severity,
                    actions, status, created_at, shown_at, acted_at, data, dedup_key, action_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.employee_id,
                    record.module,
                    record.reminder_type,
                    record.target_date,
                    record.title,
                    record.message,
                    record.severity,
                    json.dumps(record.actions, ensure_ascii=False),
                    record.status,
                    _dt_to_text(record.created_at),
                    _dt_to_text(record.shown_at),
                    _dt_to_text(record.acted_at),
                    json.dumps(record.data, ensure_ascii=False),
                    dedup_key,
                    action.id if action else record.action_id,
                ),
            )
            conn.commit()
            return True

    def list_reminders(self, employee_id: str, status: str | None = None) -> list[ReminderRecord]:
        sql = "SELECT * FROM reminders WHERE employee_id=?"
        params: list[Any] = [employee_id]
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT 50"
        now_text = _dt_to_text(_now())
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(sql, params).fetchall()
            ids = [row["id"] for row in rows if row["status"] == "pending"]
            if ids:
                conn.executemany(
                    "UPDATE reminders SET status='shown', shown_at=? WHERE id=? AND status='pending'",
                    [(now_text, reminder_id) for reminder_id in ids],
                )
                rows = conn.execute(sql, params).fetchall()
            conn.commit()
        return [self._row_to_reminder(row) for row in rows]


    def cleanup(self) -> dict[str, int]:
        now = _now()
        action_cutoff = now - timedelta(days=self.settings.action_retention_days)
        reminder_cutoff = now - timedelta(days=self.settings.reminder_retention_days)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            stale_processing_cutoff = now - timedelta(minutes=self.settings.processing_stale_minutes)
            unknown_actions = conn.execute(
                "UPDATE pending_actions SET status='unknown', error_message='PROCESSING_STALE_AFTER_RESTART', updated_at=? "
                "WHERE status='processing' AND updated_at<=?",
                (_dt_to_text(now), _dt_to_text(stale_processing_cutoff)),
            ).rowcount
            expired = conn.execute(
                "UPDATE pending_actions SET status='expired', updated_at=? "
                "WHERE status='pending' AND expires_at IS NOT NULL AND expires_at<=?",
                (_dt_to_text(now), _dt_to_text(now)),
            ).rowcount
            deleted_actions = conn.execute(
                "DELETE FROM pending_actions WHERE updated_at<? AND status IN ('succeeded','failed','cancelled','expired','unknown')",
                (_dt_to_text(action_cutoff),),
            ).rowcount
            deleted_reminders = conn.execute(
                "DELETE FROM reminders WHERE created_at<? AND status IN ('acted','dismissed','expired')",
                (_dt_to_text(reminder_cutoff),),
            ).rowcount
            deleted_chat_states = conn.execute(
                "DELETE FROM chat_states WHERE expires_at<=?",
                (_dt_to_text(now),),
            ).rowcount

            deleted_daily_deliveries = conn.execute(
                """
                DELETE FROM daily_reminder_deliveries
                WHERE delivered_at<?
                """,
                (_dt_to_text(reminder_cutoff),),
            ).rowcount

            conn.commit()
        return {
            "unknownActions": unknown_actions,
            "expiredActions": expired,
            "deletedActions": deleted_actions,
            "deletedReminders": deleted_reminders,
            "deletedChatStates": deleted_chat_states,
            "deletedDailyReminderDeliveries": (
                deleted_daily_deliveries
            ),
        }

    def count_rows(self, table: str) -> int:
        queries = {
            "pending_actions": "SELECT COUNT(*) FROM pending_actions",
            "reminders": "SELECT COUNT(*) FROM reminders",
            "chat_states": "SELECT COUNT(*) FROM chat_states",
            "daily_reminder_deliveries": (
                "SELECT COUNT(*) "
                "FROM daily_reminder_deliveries"
            ),
        }
        query = queries.get(table)
        if query is None:
            raise ValueError("invalid table")
        with self._connect() as conn:
            return int(conn.execute(query).fetchone()[0])

    def _row_to_action(self, row: sqlite3.Row) -> PendingActionRecord:
        return PendingActionRecord(
            id=row["id"],
            employee_id=row["employee_id"],
            action_type=row["action_type"],
            payload=self._json_load(row["payload"], {}),
            status=row["status"],
            created_at=_dt_from_text(row["created_at"]) or _now(),
            updated_at=_dt_from_text(row["updated_at"]) or _dt_from_text(row["created_at"]) or _now(),
            expires_at=_dt_from_text(row["expires_at"]),
            idempotency_key=row["idempotency_key"] or row["id"],
            reminder_id=row["reminder_id"],
        )

    def _row_to_reminder(self, row: sqlite3.Row) -> ReminderRecord:
        return ReminderRecord(
            id=row["id"],
            employee_id=row["employee_id"],
            module=row["module"],
            reminder_type=row["reminder_type"],
            target_date=row["target_date"],
            title=row["title"],
            message=row["message"],
            severity=row["severity"],
            actions=self._json_load(row["actions"], []),
            status=row["status"],
            created_at=_dt_from_text(row["created_at"]) or _now(),
            shown_at=_dt_from_text(row["shown_at"]),
            acted_at=_dt_from_text(row["acted_at"]),
            data=self._json_load(row["data"], {}),
            action_id=row["action_id"],
        )

    @staticmethod
    def _json_load(value: str | None, default: Any) -> Any:
        if not value:
            return default
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return default

    @staticmethod
    def _dedup_key(record: ReminderRecord) -> str:
        return f"{record.module}:{record.reminder_type}:{record.target_date or 'none'}"