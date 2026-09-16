from pathlib import Path


ROOT = Path(r"D:\serviceAi")

REPOSITORY_FILE = (
    ROOT
    / "app"
    / "infrastructure"
    / "repositories"
    / "state_repository.py"
)

REMINDER_SERVICE_FILE = (
    ROOT
    / "app"
    / "application"
    / "services"
    / "reminder_service.py"
)

MODELS_FILE = ROOT / "app" / "domain" / "models.py"
AGENT_ROUTE_FILE = ROOT / "app" / "api" / "routes" / "agent.py"


def replace_once(
    text: str,
    old: str,
    new: str,
    label: str,
) -> str:
    count = text.count(old)

    if count != 1:
        raise RuntimeError(
            f"{label}: expected exactly one match, found {count}"
        )

    return text.replace(old, new, 1)


def replace_all(
    text: str,
    old: str,
    new: str,
    minimum_count: int,
    label: str,
) -> str:
    count = text.count(old)

    if count < minimum_count:
        raise RuntimeError(
            f"{label}: expected at least "
            f"{minimum_count} matches, found {count}"
        )

    return text.replace(old, new)


def patch_repository(text: str) -> str:
    text = replace_once(
        text,
        "SCHEMA_VERSION = 4",
        "SCHEMA_VERSION = 5",
        "repository schema version",
    )

    text = replace_once(
        text,
        """                CREATE INDEX IF NOT EXISTS idx_chat_states_expires_at ON chat_states(expires_at);
                \"\"\"
""",
        """                CREATE INDEX IF NOT EXISTS idx_chat_states_expires_at ON chat_states(expires_at);

                CREATE TABLE IF NOT EXISTS daily_reminder_deliveries (
                    employee_id TEXT NOT NULL,
                    target_date TEXT NOT NULL,
                    delivered_at TEXT NOT NULL,
                    reminder_count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(employee_id, target_date)
                );
                CREATE INDEX IF NOT EXISTS idx_daily_reminder_deliveries_date
                ON daily_reminder_deliveries(target_date);
                \"\"\"
""",
        "daily reminder delivery table",
    )

    repository_methods = '''
    def has_daily_reminder_delivery(
        self,
        employee_id: str,
        target_date: str,
    ) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
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

'''

    text = replace_once(
        text,
        "    def save_reminder(self, record: ReminderRecord, dedup_hours: int) -> bool:\n",
        repository_methods
        + "    def save_reminder(self, record: ReminderRecord, dedup_hours: int) -> bool:\n",
        "repository daily reminder methods",
    )

    text = replace_once(
        text,
        '''            deleted_chat_states = conn.execute(
                "DELETE FROM chat_states WHERE expires_at<=?",
                (_dt_to_text(now),),
            ).rowcount
            conn.commit()
''',
        '''            deleted_chat_states = conn.execute(
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
''',
        "daily delivery cleanup",
    )

    text = replace_once(
        text,
        '''            "deletedChatStates": deleted_chat_states,
        }
''',
        '''            "deletedChatStates": deleted_chat_states,
            "deletedDailyReminderDeliveries": (
                deleted_daily_deliveries
            ),
        }
''',
        "daily delivery cleanup result",
    )

    text = replace_once(
        text,
        '''            "chat_states": "SELECT COUNT(*) FROM chat_states",
        }
''',
        '''            "chat_states": "SELECT COUNT(*) FROM chat_states",
            "daily_reminder_deliveries": (
                "SELECT COUNT(*) "
                "FROM daily_reminder_deliveries"
            ),
        }
''',
        "daily delivery row count",
    )

    return text


def patch_reminder_service(text: str) -> str:
    old_check = '''    async def check(
        self,
        context: AgentContext,
        snapshot: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        date = context.date

        if not date:
            return []

        if snapshot is None:
            snapshot = await self.snapshots.fetch(
                context,
                date,
            )

        created: list[ReminderRecord] = []

        for record, action in self._build_records(
            context,
            date,
            snapshot,
        ):
            if action is not None:
                saved = await asyncio.to_thread(
                    self.repository.save_reminder_with_action,
                    record,
                    action,
                    self.settings.reminder_dedup_hours,
                )
            else:
                saved = await asyncio.to_thread(
                    self.repository.save_reminder,
                    record,
                    self.settings.reminder_dedup_hours,
                )

            if saved:
                created.append(record)

        return [
            record.model_dump(mode="json")
            for record in created
        ]

'''

    new_check = '''    async def check(
        self,
        context: AgentContext,
        snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        date = context.date
        employee_id = str(
            context.employee_id or ""
        ).strip()

        empty_result: dict[str, Any] = {
            "show": False,
            "greeting": None,
            "intro": None,
            "date": date,
            "reminders": [],
        }

        if not date or not employee_id:
            return empty_result

        already_delivered = await asyncio.to_thread(
            self.repository.has_daily_reminder_delivery,
            employee_id,
            date,
        )

        if already_delivered:
            return empty_result

        if snapshot is None:
            snapshot = await self.snapshots.fetch(
                context,
                date,
            )

        for record, action in self._build_records(
            context,
            date,
            snapshot,
        ):
            if action is not None:
                await asyncio.to_thread(
                    self.repository.save_reminder_with_action,
                    record,
                    action,
                    self.settings.reminder_dedup_hours,
                )
            else:
                await asyncio.to_thread(
                    self.repository.save_reminder,
                    record,
                    self.settings.reminder_dedup_hours,
                )

        records = await asyncio.to_thread(
            self.repository.list_reminders_for_date,
            employee_id,
            date,
        )

        claimed = await asyncio.to_thread(
            self.repository.claim_daily_reminder_delivery,
            employee_id,
            date,
            len(records),
        )

        if not claimed:
            return empty_result

        records = await asyncio.to_thread(
            self.repository.list_reminders_for_date,
            employee_id,
            date,
        )

        reminders = [
            record.model_dump(mode="json")
            for record in records
        ]

        if not reminders:
            return empty_result

        return {
            "show": True,
            "greeting": "سلام 👋",
            "intro": (
                "چند یادآوری کوچیک برای امروز داری:"
            ),
            "date": date,
            "reminders": reminders,
        }

'''

    text = replace_once(
        text,
        old_check,
        new_check,
        "daily reminder check logic",
    )

    text = replace_once(
        text,
        '''                title="یادآوری رزرو غذا",
                message=(
                    f"برای {date} هنوز غذایی رزرو نشده است. "
                    f"«{food_name}» در منو ظرفیت دارد."
                ),
''',
        '''                title="رزرو غذای امروز",
                message=(
                    "غذای امروزت هنوز رزرو نشده. "
                    f"«{food_name}» هنوز ظرفیت داره؛ "
                    "بد نیست زودتر رزروش کنی."
                ),
''',
        "friendly food message",
    )

    text = replace_once(
        text,
        '''                    title="بررسی تردد",
                    message=(
                        f"برای {date} ترددی پیدا نشد."
                    ),
''',
        '''                    title="تردد ثبت‌نشده",
                    message=(
                        f"برای {date} ترددی ثبت نشده؛ "
                        "بد نیست یه نگاه بندازی و مطمئن "
                        "بشی چیزی جا نمونده."
                    ),
''',
        "friendly missing attendance message",
    )

    text = replace_once(
        text,
        '''                    title="تردد ناقص",
                    message=(
                        f"برای {date} فقط یک تردد با ساعت "
                        f"{event_time} پیدا شد."
                    ),
''',
        '''                    title="تردد ناقص",
                    message=(
                        f"برای {date} فقط یک تردد در ساعت "
                        f"{event_time} ثبت شده؛ لطفاً ورود "
                        "و خروجت رو بررسی کن."
                    ),
''',
        "friendly incomplete attendance message",
    )

    text = replace_once(
        text,
        '''                title="درخواست در جریان",
                message=(
                    f"{len(sent)} درخواست مرخصی یا مأموریت "
                    "در وضعیت ارسال‌شده دارید."
                ),
''',
        '''                title="درخواست در حال بررسی",
                message=(
                    f"{len(sent)} درخواست مرخصی یا مأموریتت "
                    "هنوز در حال بررسیه؛ بد نیست وضعیتش "
                    "رو چک کنی."
                ),
''',
        "friendly leave message",
    )

    text = replace_once(
        text,
        '''                title="یادآوری پایان ماه",
                message=(
                    "ماه رو به پایان است. تردد، مرخصی و "
                    "مأموریت‌های ثبت‌نشده را بررسی کنید."
                ),
''',
        '''                title="مرور پایان ماه",
                message=(
                    "به آخر ماه نزدیک شدیم؛ یادت نره "
                    "ترددها، مرخصی‌ها و مأموریت‌هات رو "
                    "یک بار مرور کنی."
                ),
''',
        "friendly month end message",
    )

    text = replace_all(
        text,
        '''                    {
                        "type": "DISMISS",
                        "label": "بعداً",
                    },
''',
        "",
        3,
        "remove later actions",
    )

    text = replace_all(
        text,
        '''                        {
                            "type": "DISMISS",
                            "label": "بعداً",
                        },
''',
        "",
        1,
        "remove nested later action",
    )

    text = replace_all(
        text,
        '''                        {
                            "type": "DISMISS",
                            "label": "نادیده بگیر",
                        },
''',
        "",
        1,
        "remove dismiss action",
    )

    return text


def patch_models(text: str) -> str:
    old_model = '''class ReminderListRequest(EmployeeRequestBase):
    """
    Request مخصوص POST /api/agent/reminders.
    """

    status: str | None = Field(
        default=None,
        pattern=(
            "^(pending|shown|acted|"
            "dismissed|expired)$"
        ),
    )

'''

    new_model = '''class ReminderListRequest(EmployeeRequestBase):
    """
    Request مخصوص POST /api/agent/reminders.

    وضعیت Reminder داخلی است و مصرف‌کننده API
    نیازی به ارسال status ندارد.
    """

    pass

'''

    return replace_once(
        text,
        old_model,
        new_model,
        "remove reminder status request field",
    )


def patch_agent_route(text: str) -> str:
    text = replace_once(
        text,
        '''    description=(
        "وضعیت غذا، تردد، مرخصی و پایان ماه را بررسی می‌کند "
        "و در صورت نیاز یادآوری جدید ایجاد می‌کند."
    ),
''',
        '''    description=(
        "در اولین ورود کاربر در هر روز، وضعیت غذا، تردد، "
        "مرخصی و پایان ماه را بررسی می‌کند و یادآوری‌های "
        "لازم را فقط یک بار به اپلیکیشن تحویل می‌دهد."
    ),
''',
        "reminder check swagger description",
    )

    text = replace_once(
        text,
        '''    snapshot = await container.snapshot_service.fetch(
        context,
        str(context.date),
    )

    reminders = await container.reminder_service.check(
        context,
        snapshot=snapshot,
    )

    return ok(
        {
            "reminders": reminders,
        },
        "یادآوری‌ها بررسی و ایجاد شدند.",
    )
''',
        '''    data = await container.reminder_service.check(
        context
    )

    return ok(
        data,
        (
            "وضعیت یادآوری‌های روزانه بررسی شد."
        ),
    )
''',
        "daily reminder route response",
    )

    text = replace_once(
        text,
        '''@router.post(
    "/reminders",
    response_model=ApiResponse[list[dict[str, Any]]],
)
''',
        '''@router.post(
    "/reminders",
    summary="دریافت یادآوری‌های فعال",
    description=(
        "یادآوری‌های فعال کاربر را برمی‌گرداند. "
        "وضعیت Reminder داخلی است و در Request ارسال نمی‌شود."
    ),
    response_model=ApiResponse[list[dict[str, Any]]],
)
''',
        "reminder list swagger description",
    )

    text = replace_once(
        text,
        '''    data = await container.reminder_service.list_reminders(
        employee_id,
        status=request.status,
    )
''',
        '''    data = await container.reminder_service.list_reminders(
        employee_id
    )
''',
        "remove status route usage",
    )

    text = replace_once(
        text,
        '''@router.post(
    "/reminders/dismiss",
    response_model=ApiResponse[dict[str, Any]],
)
''',
        '''@router.post(
    "/reminders/dismiss",
    summary="نادیده گرفتن یادآوری - اختیاری",
    description=(
        "برای سازگاری نگه داشته شده است. در جریان جدید "
        "اپلیکیشن، استفاده از این Endpoint الزامی نیست."
    ),
    response_model=ApiResponse[dict[str, Any]],
)
''',
        "dismiss swagger description",
    )

    return text


def main() -> None:
    repository = REPOSITORY_FILE.read_text(
        encoding="utf-8"
    )
    reminder_service = REMINDER_SERVICE_FILE.read_text(
        encoding="utf-8"
    )
    models = MODELS_FILE.read_text(
        encoding="utf-8"
    )
    agent_route = AGENT_ROUTE_FILE.read_text(
        encoding="utf-8"
    )

    repository = patch_repository(repository)
    reminder_service = patch_reminder_service(
        reminder_service
    )
    models = patch_models(models)
    agent_route = patch_agent_route(agent_route)

    REPOSITORY_FILE.write_text(
        repository,
        encoding="utf-8",
    )
    REMINDER_SERVICE_FILE.write_text(
        reminder_service,
        encoding="utf-8",
    )
    MODELS_FILE.write_text(
        models,
        encoding="utf-8",
    )
    AGENT_ROUTE_FILE.write_text(
        agent_route,
        encoding="utf-8",
    )

    print("PATCH COMPLETED SUCCESSFULLY")
    print("Modified files:")
    print(REPOSITORY_FILE)
    print(REMINDER_SERVICE_FILE)
    print(MODELS_FILE)
    print(AGENT_ROUTE_FILE)


if __name__ == "__main__":
    main()