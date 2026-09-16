from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.application.services.action_service import ActionService
from app.application.services.snapshot_service import SnapshotService
from app.core.config import Settings
from app.domain.models import (
    AgentContext,
    PendingActionRecord,
    ReminderRecord,
)
from app.domain.text import (
    is_jalali_month_end,
    parse_float,
    parse_int,
    sap_duration_to_time,
)
from app.infrastructure.repositories.state_repository import (
    StateRepository,
)


ReminderWithAction = tuple[
    ReminderRecord,
    PendingActionRecord | None,
]


class ReminderService:
    def __init__(
        self,
        settings: Settings,
        repository: StateRepository,
        snapshots: SnapshotService,
        actions: ActionService,
    ):
        self.settings = settings
        self.repository = repository
        self.snapshots = snapshots
        self.actions = actions

    async def check(
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
            record._to_public_reminder(record)
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

    async def check(
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
            self._to_public_reminder(record)
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

    async def list_reminders(
        self,
        employee_id: str,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = await asyncio.to_thread(
            self.repository.list_reminders,
            employee_id,
            status,
        )

        return [
            self._to_public_reminder(record)
            for record in rows
        ]

    @staticmethod
    def _to_public_reminder(
        record: ReminderRecord,
    ) -> dict[str, Any]:
        public_actions: list[dict[str, Any]] = []

        for action in record.actions or []:
            if not isinstance(action, dict):
                continue

            action_type = str(
                action.get("type") or ""
            ).strip()

            if not action_type:
                continue

            if action_type.upper() == "DISMISS":
                continue

            public_action: dict[str, Any] = {
                "type": action_type,
            }

            label = action.get("label")

            if label is not None:
                public_action["label"] = label

            payload = action.get("payload")

            if payload is not None:
                public_action["payload"] = payload

            action_id = action.get("actionId")

            if action_id is not None:
                public_action["actionId"] = action_id

            public_actions.append(public_action)

        return {
            "id": record.id,
            "module": record.module,
            "reminderType": record.reminder_type,
            "targetDate": record.target_date,
            "title": record.title,
            "message": record.message,
            "severity": record.severity,
            "actions": public_actions,
        }


    def _build_records(
        self,
        context: AgentContext,
        date: str,
        snapshot: dict[str, Any],
    ) -> Iterator[ReminderWithAction]:
        yield from self._food_records(
            context,
            date,
            snapshot.get("food") or {},
        )

        yield from self._attendance_records(
            context,
            date,
            snapshot.get("attendance") or {},
        )

        yield from self._leave_records(
            context,
            date,
            snapshot.get("leave") or {},
        )

        yield from self._month_end_records(
            context,
            date,
        )

    def _food_records(
        self,
        context: AgentContext,
        date: str,
        source: dict[str, Any],
    ) -> Iterator[ReminderWithAction]:
        menu = source.get("data")

        if source.get("error") or not isinstance(menu, dict):
            return

        days = menu.get("days") or []

        if not isinstance(days, list):
            return

        for day in days:
            if not isinstance(day, dict):
                continue

            if day.get("date") != date:
                continue

            if day.get("selectedPlanDetailId"):
                continue

            available_foods: list[dict[str, Any]] = []

            for food in day.get("foods") or []:
                if not isinstance(food, dict):
                    continue

                remain_count = parse_int(
                    food.get("remainCount")
                )

                if remain_count is None or remain_count > 0:
                    available_foods.append(food)

            if not available_foods:
                continue

            best = max(
                available_foods,
                key=lambda item: (
                    parse_float(item.get("rate")) or 0.0
                ),
            )

            plan_detail_id = best.get("planDetailId")

            if plan_detail_id is None:
                continue

            food_name = (
                best.get("foodName")
                or "غذای امروز"
            )

            reminder_id = uuid4().hex

            action = (
                self.actions.new_pending_action_record(
                    employee_id=str(
                        context.employee_id
                    ),
                    action_type="RESERVE_FOOD",
                    payload={
                        "planDetailId": plan_detail_id,
                    },
                    reminder_id=reminder_id,
                )
            )

            record = ReminderRecord(
                id=reminder_id,
                employee_id=str(context.employee_id),
                module="food",
                reminder_type="food_not_reserved",
                target_date=date,
                title="رزرو غذای امروز",
                message=(
                    "غذای امروزت هنوز رزرو نشده. "
                    f"«{food_name}» هنوز ظرفیت داره؛ "
                    "بد نیست زودتر رزروش کنی."
                ),
                severity="warning",
                actions=[
                    {
                        "type": "CONFIRM_ACTION",
                        "label": "تأیید و رزرو",
                        "actionId": action.id,
                    },
                ],
                status="pending",
                created_at=datetime.now(
                    timezone.utc
                ),
                data={
                    "date": date,
                    "candidate": {
                        "planDetailId": plan_detail_id,
                        "foodName": food_name,
                        "remainCount": best.get(
                            "remainCount"
                        ),
                    },
                },
                action_id=action.id,
            )

            yield record, action

    def _attendance_records(
        self,
        context: AgentContext,
        date: str,
        source: dict[str, Any],
    ) -> Iterator[ReminderWithAction]:
        events = source.get("data")

        if source.get("error") or not isinstance(
            events,
            dict,
        ):
            return

        rows = events.get("data") or []

        if not isinstance(rows, list):
            return

        if not rows:
            yield (
                ReminderRecord(
                    id=uuid4().hex,
                    employee_id=str(
                        context.employee_id
                    ),
                    module="attendance",
                    reminder_type="attendance_missing",
                    target_date=date,
                    title="تردد ثبت‌نشده",
                    message=(
                        f"برای {date} ترددی ثبت نشده؛ "
                        "بد نیست یه نگاه بندازی و مطمئن "
                        "بشی چیزی جا نمونده."
                    ),
                    severity="warning",
                    actions=[
                        {
                            "type": "OPEN_PAGE",
                            "label": "بررسی تردد",
                            "payload": {
                                "page": "attendance",
                            },
                        },
                    ],
                    created_at=datetime.now(
                        timezone.utc
                    ),
                    data={
                        "eventCount": 0,
                    },
                ),
                None,
            )

            return

        if len(rows) == 1:
            first_event = rows[0]

            if not isinstance(first_event, dict):
                return

            event_time = sap_duration_to_time(
                first_event.get("eventTime")
            )

            yield (
                ReminderRecord(
                    id=uuid4().hex,
                    employee_id=str(
                        context.employee_id
                    ),
                    module="attendance",
                    reminder_type=(
                        "attendance_incomplete"
                    ),
                    target_date=date,
                    title="تردد ناقص",
                    message=(
                        f"برای {date} فقط یک تردد در ساعت "
                        f"{event_time} ثبت شده؛ لطفاً ورود "
                        "و خروجت رو بررسی کن."
                    ),
                    severity="warning",
                    actions=[
                        {
                            "type": "OPEN_PAGE",
                            "label": "ثبت تردد",
                            "payload": {
                                "page": "attendance",
                            },
                        },
                    ],
                    created_at=datetime.now(
                        timezone.utc
                    ),
                    data={
                        "eventCount": 1,
                        "eventTime": event_time,
                    },
                ),
                None,
            )

    def _leave_records(
        self,
        context: AgentContext,
        date: str,
        source: dict[str, Any],
    ) -> Iterator[ReminderWithAction]:
        leave_response = source.get("data")

        if source.get("error") or not isinstance(
            leave_response,
            dict,
        ):
            return

        rows = leave_response.get("data") or []

        if not isinstance(rows, list):
            return

        sent = [
            row
            for row in rows
            if isinstance(row, dict)
            and str(
                row.get("statusID") or ""
            ).upper()
            == "SENT"
        ]

        if not sent:
            return

        yield (
            ReminderRecord(
                id=uuid4().hex,
                employee_id=str(
                    context.employee_id
                ),
                module="leave",
                reminder_type="leave_pending",
                target_date=date,
                title="درخواست در حال بررسی",
                message=(
                    f"{len(sent)} درخواست مرخصی یا مأموریتت "
                    "هنوز در حال بررسیه؛ بد نیست وضعیتش "
                    "رو چک کنی."
                ),
                severity="info",
                actions=[
                    {
                        "type": "OPEN_PAGE",
                        "label": "نمایش درخواست‌ها",
                        "payload": {
                            "page": "leave-requests",
                        },
                    },
                ],
                created_at=datetime.now(
                    timezone.utc
                ),
                data={
                    "sentCount": len(sent),
                },
            ),
            None,
        )

    def _month_end_records(
        self,
        context: AgentContext,
        date: str,
    ) -> Iterator[ReminderWithAction]:
        # تشخیص پایان ماه فقط بر اساس تاریخ انجام می‌شود.
        # مصرف‌کننده API هیچ ورودی دستی برای فعال‌سازی
        # Reminder پایان ماه ارسال نمی‌کند.
        is_month_end = is_jalali_month_end(
            date,
            self.settings.month_end_reminder_days,
        )

        if not is_month_end:
            return

        yield (
            ReminderRecord(
                id=uuid4().hex,
                employee_id=str(
                    context.employee_id
                ),
                module="general",
                reminder_type="month_end_review",
                target_date=date,
                title="مرور پایان ماه",
                message=(
                    "به آخر ماه نزدیک شدیم؛ یادت نره "
                    "ترددها، مرخصی‌ها و مأموریت‌هات رو "
                    "یک بار مرور کنی."
                ),
                severity="info",
                actions=[
                    {
                        "type": "OPEN_PAGE",
                        "label": "بررسی موارد",
                        "payload": {
                            "page": "agent-month-end",
                        },
                    },
                ],
                created_at=datetime.now(
                    timezone.utc
                ),
                data={
                    "source": (
                        "automatic-month-end-detection"
                    ),
                    "monthEndReminderDays": (
                        self.settings
                        .month_end_reminder_days
                    ),
                },
            ),
            None,
        )