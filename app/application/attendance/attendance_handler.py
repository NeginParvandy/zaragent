from __future__ import annotations

from typing import Any


class AttendanceHandler:

    def __init__(
        self,
        attendance_service,
        action_service,
        repository=None,
    ):
        self.attendance_service = attendance_service
        self.action_service = action_service
        self.repository = repository


    def can_handle(
        self,
        text: str,
    ) -> bool:
        from .attendance_rules import (
            is_attendance_text,
        )

        return is_attendance_text(text)


    async def _handle_future_attendance_guard(
        self,
        context,
        nlu_result: dict[str, Any],
    ) -> dict[str, Any] | None:

        if not isinstance(
            nlu_result,
            dict,
        ):
            return None

        domain = str(
            nlu_result.get("domain")
            or ""
        )

        intent = str(
            nlu_result.get("intent")
            or ""
        )

        if domain != "ATTENDANCE":
            return None

        if intent not in {
            "CREATE_TIME_EVENT",
            "CREATE_TIME_EVENT_RANGE",
        }:
            return None

        entities = (
            nlu_result.get("entities")
            if isinstance(
                nlu_result.get("entities"),
                dict,
            )
            else {}
        )

        event_date = (
            entities.get("date")
            or entities.get("eventDate")
        )

        event_time = (
            entities.get("time")
            or entities.get("startTime")
            or entities.get("endTime")
        )

        reason = (
            self.action_service
            .attendance_future_reason(
                event_date,
                event_time,
                today=str(
                    context.date
                    or ""
                ),
            )
        )

        if reason is None:
            return None

        return {
            "reply": (
                "ثبت تردد برای زمان آینده "
                "امکان‌پذیر نیست. لطفاً تاریخ "
                "و ساعت گذشته یا زمان فعلی "
                "را اعلام کنید."
            ),
            "requiresConfirmation": False,
            "data": {
                "domain": "ATTENDANCE",
                "intent": intent,
                "blocked": True,
                "reasonCode": (
                    "FUTURE_ATTENDANCE_NOT_ALLOWED"
                ),
                "reason": reason,
                "eventDate": event_date,
                "eventTime": event_time,
            },
        }


    async def handle(
        self,
        context,
        text: str,
        dates: list[str],
        times: list[str],
        *,
        force_create: bool = False,
        event_type: str | None = None,
    ) -> dict[str, Any]:

        target_dates = (
            dates
            or (
                [str(context.date)]
                if context.date
                else []
            )
        )

        is_create = (
            force_create
            or "ثبت" in text
            or "بزن" in text
        )

        if is_create:

            future_response = (
                await self._handle_future_attendance_guard(
                    context,
                    {
                        "domain": "ATTENDANCE",
                        "intent": "CREATE_TIME_EVENT",
                        "entities": {
                            "date": (
                                target_dates[0]
                                if target_dates
                                else None
                            ),
                            "time": (
                                times[0]
                                if times
                                else None
                            ),
                        },
                    },
                )
            )

            if future_response is not None:
                return future_response


        if not is_create:

            if not target_dates:
                return {
                    "reply": (
                        "برای بررسی تردد، تاریخ "
                        "را وارد کنید."
                    ),
                    "requiresConfirmation": False,
                }

            end_date = (
                target_dates[1]
                if len(target_dates) > 1
                else target_dates[0]
            )

            events = await self.attendance_service.get_time_events(
                context,
                target_dates[0],
                end_date,
            )

            rows = events.get("data") or []

            return {
                "reply": (
                    f"{len(rows) if isinstance(rows, list) else 0} "
                    "تردد دریافت شد."
                ),
                "requiresConfirmation": False,
                "data": {
                    "events": rows,
                },
            }


        if not target_dates or not times:
            return {
                "reply": (
                    "برای ثبت تردد، تاریخ و "
                    "ساعت لازم است."
                ),
                "requiresConfirmation": False,
            }


        events = await self.attendance_service.get_time_events(
            context,
            target_dates[0],
            target_dates[0],
        )

        rows = events.get("data") or []


        valid, existing = (
            self.attendance_service
            .validate_time_event_distance(
                rows
                if isinstance(rows, list)
                else [],
                times[0],
            )
        )


        if not valid:
            return {
                "reply": (
                    f"تردد {existing} برای همین روز "
                    "وجود دارد و فاصله کمتر از "
                    "یک دقیقه مجاز نیست."
                ),
                "requiresConfirmation": False,
            }


        payload = {
            "eventDate": target_dates[0],
            "eventTime": times[0],
            "eventType": event_type,
            "note": "",
        }


        action = (
            await self.action_service.create_pending_action(
                str(context.employee_id),
                "CREATE_TIME_EVENT",
                payload,
            )
        )


        event_type_label = {
            "ENTRY": "ورود",
            "EXIT": "خروج",
        }.get(
            str(event_type or ""),
            "تردد",
        )


        return {
            "reply": (
                f"ثبت {event_type_label} برای "
                f"{target_dates[0]} ساعت "
                f"{times[0]} "
                "انجام شود؟"
            ),
            "requiresConfirmation": True,
            "pendingAction": {
                "id": action["id"],
                "label": "تأیید و ثبت تردد",
                "expiresAt": action.get(
                    "expiresAt"
                ),
            },
            "data": {
                "date": target_dates[0],
                "time": times[0],
                "eventType": event_type,
            },
        }