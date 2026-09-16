from __future__ import annotations

from typing import Any

from app.application.services.reminder_service import ReminderService
from app.application.services.snapshot_service import SnapshotService
from app.domain.models import AgentContext
from app.domain.text import parse_bool, parse_float, parse_int, sap_duration_to_time


class DailyBriefService:
    def __init__(self, snapshots: SnapshotService, reminders: ReminderService):
        self.snapshots = snapshots
        self.reminders = reminders

    async def build(
        self,
        context: AgentContext,
        *,
        snapshot: dict[str, Any] | None = None,
        create_reminders: bool = True,
    ) -> dict[str, Any]:
        date = context.date
        if not date:
            return {
                "title": "گزارش امروز",
                "severity": "warning",
                "summary": "برای ساخت گزارش روزانه، تاریخ شمسی امروز باید ارسال شود.",
                "cards": [],
                "reminders": [],
            }
        snapshot = snapshot or await self.snapshots.fetch(context, date)
        cards = [
            self._food_card(date, snapshot.get("food") or {}),
            self._attendance_card(date, snapshot.get("attendance") or {}),
            self._leave_card(snapshot.get("leave") or {}),
        ]
        reminders = await self.reminders.check(context, snapshot=snapshot) if create_reminders else []
        return {
            "title": "گزارش امروز شما",
            "date": date,
            "severity": self._max_severity(cards),
            "summary": self._summary(cards),
            "cards": cards,
            "reminders": reminders,
        }

    def _food_card(self, date: str, source: dict[str, Any]) -> dict[str, Any]:
        menu = source.get("data")
        if source.get("error") or not isinstance(menu, dict):
            return self._error_card("food", "رزرو غذا", "امکان دریافت منوی غذا فراهم نشد.", source.get("error"))
        day = next((item for item in menu.get("days") or [] if item.get("date") == date), None)
        if not day:
            return {
                "module": "food",
                "title": "رزرو غذا",
                "message": "برای تاریخ امروز در منو غذایی پیدا نشد.",
                "severity": "info",
                "actions": [{"type": "OPEN_PAGE", "label": "مشاهده منو", "payload": {"page": "food"}}],
                "data": {"date": date},
            }
        selected_id = day.get("selectedPlanDetailId")
        if selected_id:
            selected = next((food for food in day.get("foods") or [] if str(food.get("planDetailId")) == str(selected_id)), None)
            return {
                "module": "food",
                "title": "رزرو غذا",
                "message": f"برای امروز «{selected.get('foodName') if selected else 'غذای انتخاب‌شده'}» رزرو شده است.",
                "severity": "success",
                "actions": [{"type": "OPEN_PAGE", "label": "مشاهده منو", "payload": {"page": "food"}}],
                "data": {"date": date, "selectedPlanDetailId": selected_id},
            }
        available = [
            food
            for food in day.get("foods") or []
            if parse_int(food.get("remainCount")) is None or (parse_int(food.get("remainCount")) or 0) > 0
        ]
        if not available:
            return {
                "module": "food",
                "title": "رزرو غذا",
                "message": "برای امروز غذایی با ظرفیت قابل رزرو پیدا نشد.",
                "severity": "warning",
                "actions": [{"type": "OPEN_PAGE", "label": "مشاهده منو", "payload": {"page": "food"}}],
                "data": {"date": date},
            }
        best = max(available, key=lambda item: parse_float(item.get("rate")))
        return {
            "module": "food",
            "title": "رزرو غذا",
            "message": f"برای امروز هنوز غذا رزرو نشده. «{best.get('foodName') or 'غذای امروز'}» ظرفیت دارد.",
            "severity": "warning",
            "actions": [{"type": "OPEN_PAGE", "label": "رزرو غذا", "payload": {"page": "food", "date": date}}],
            "data": {
                "date": date,
                "candidate": {
                    "planDetailId": best.get("planDetailId"),
                    "foodName": best.get("foodName"),
                    "remainCount": best.get("remainCount"),
                },
            },
        }

    def _attendance_card(self, date: str, source: dict[str, Any]) -> dict[str, Any]:
        events = source.get("data")
        if source.get("error") or not isinstance(events, dict):
            return self._error_card("attendance", "تردد", "امکان دریافت تردد فراهم نشد.", source.get("error"))
        rows = events.get("data") or []
        if not rows:
            return {
                "module": "attendance",
                "title": "تردد",
                "message": "برای امروز ترددی پیدا نشد.",
                "severity": "warning",
                "actions": [{"type": "OPEN_PAGE", "label": "بررسی تردد", "payload": {"page": "attendance"}}],
                "data": {"eventCount": 0},
            }
        times = [time for time in (sap_duration_to_time(row.get("eventTime")) for row in rows) if time]
        incomplete = len(rows) == 1
        message = f"ترددهای امروز: {'، '.join(times)}."
        if incomplete:
            message += " فقط یک رکورد دیده می‌شود."
        return {
            "module": "attendance",
            "title": "تردد",
            "message": message,
            "severity": "warning" if incomplete else "success",
            "actions": [{"type": "OPEN_PAGE", "label": "نمایش تردد", "payload": {"page": "attendance"}}],
            "data": {"eventCount": len(rows), "times": times},
        }

    def _leave_card(self, source: dict[str, Any]) -> dict[str, Any]:
        leave_response = source.get("data")
        if source.get("error") or not isinstance(leave_response, dict):
            return self._error_card("leave", "مرخصی و مأموریت", "امکان دریافت درخواست‌ها فراهم نشد.", source.get("error"))
        rows = leave_response.get("data") or []
        if not rows:
            return {
                "module": "leave",
                "title": "مرخصی و مأموریت",
                "message": "درخواستی پیدا نشد.",
                "severity": "info",
                "actions": [{"type": "OPEN_PAGE", "label": "ثبت درخواست", "payload": {"page": "leave"}}],
                "data": {"requestCount": 0},
            }
        sent_count = sum(1 for row in rows if str(row.get("statusID") or "").upper() == "SENT")
        deletable_count = sum(1 for row in rows if parse_bool(row.get("isDeletable")))
        return {
            "module": "leave",
            "title": "مرخصی و مأموریت",
            "message": f"{len(rows)} درخواست پیدا شد؛ {sent_count} مورد در وضعیت Sent و {deletable_count} مورد قابل حذف است.",
            "severity": "info" if sent_count else "success",
            "actions": [{"type": "OPEN_PAGE", "label": "نمایش درخواست‌ها", "payload": {"page": "leave-requests"}}],
            "data": {"requestCount": len(rows), "sentCount": sent_count, "deletableCount": deletable_count},
        }

    @staticmethod
    def _error_card(module: str, title: str, message: str, error: Any) -> dict[str, Any]:
        return {"module": module, "title": title, "message": message, "severity": "warning", "actions": [], "data": {"sourceError": error}}

    @staticmethod
    def _summary(cards: list[dict[str, Any]]) -> str:
        warnings = [card for card in cards if card.get("severity") in {"warning", "danger"}]
        if warnings:
            return f"{len(warnings)} مورد نیازمند توجه دارید."
        return "وضعیت امروز شما خوب است و مورد فوری دیده نشد."

    @staticmethod
    def _max_severity(cards: list[dict[str, Any]]) -> str:
        levels = {"danger": 3, "warning": 2, "info": 1, "success": 0}
        return max((card.get("severity") or "info" for card in cards), key=lambda item: levels.get(item, 0), default="info")
