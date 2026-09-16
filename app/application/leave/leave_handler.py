from __future__ import annotations

import re
from typing import Any

from app.core.exceptions import AppError
from app.domain.text import (
    hours_between,
    parse_bool,
    validate_jalali_range,
)


class LeaveHandler:

    def __init__(
        self,
        leave_service,
        action_service,
        formatter=None,
    ):
        self.leave_service = leave_service
        self.action_service = action_service
        self.formatter = formatter


    def can_handle(
        self,
        text: str,
    ) -> bool:

        from .leave_rules import (
            is_leave_balance,
            is_leave_create,
            is_leave_list,
            is_delete_leave,
        )

        return any(
            [
                is_leave_balance(text),
                is_leave_create(text),
                is_leave_list(text),
                is_delete_leave(text),
            ]
        )


    def is_balance_request(
        self,
        text: str,
    ) -> bool:

        from .leave_rules import is_leave_balance

        return is_leave_balance(text)


    def can_create(
        self,
        text: str,
    ) -> bool:

        from .leave_rules import is_leave_create

        return is_leave_create(text)

    def can_delete(
            self,
            text: str,
    ) -> bool:
        from .leave_rules import is_delete_leave

        return is_delete_leave(text)

    def can_list(
            self,
            text: str,
    ) -> bool:

        from .leave_rules import is_leave_list

        return is_leave_list(text)

    async def get_balance(
        self,
        context,
        date: str,
    ) -> dict[str, Any]:

        data = await self.leave_service.get_time_account(
            context,
            date,
        )

        if self.formatter:
            return self.formatter(data)

        return {
            "reply": "اطلاعات مانده مرخصی دریافت شد.",
            "requiresConfirmation": False,
            "data": data,
        }


    def _extract_additional_values(
        self,
        text: str,
        leave_type: dict[str, Any],
    ) -> dict[str, Any]:

        values: dict[str, Any] = {}

        definitions = (
            leave_type.get(
                "toAdditionalFieldsDefinition"
            )
            or {}
        ).get("results") or []


        for item in (
            definitions
            if isinstance(definitions, list)
            else []
        ):

            if not isinstance(item, dict):
                continue

            key = (
                item.get("fieldName")
                or item.get("fieldname")
                or item.get("name")
                or item.get("field")
            )

            label = (
                item.get("fieldLabel")
                or item.get("label")
                or item.get("title")
                or ""
            )

            if key and (
                "محل" in str(label)
                or str(key).upper() == "CUSTOMER02"
            ):

                match = re.search(
                    r"(?:محل|مکان)\s+([^،\n]+)",
                    text,
                )

                values[str(key)] = (
                    match.group(1).strip()
                    if match
                    else ""
                )

            elif key:

                values[str(key)] = ""

        return values


    async def create_leave(
        self,
        context,
        text: str,
        dates: list[str],
        times: list[str],
    ) -> dict[str, Any]:

        target_dates = (
            dates
            or (
                [str(context.date)]
                if context.date
                else []
            )
        )


        if not target_dates:

            return {
                "reply": (
                    "برای ثبت درخواست، تاریخ لازم است."
                ),
                "requiresConfirmation": False,
            }


        leave_types = await self.leave_service.get_leave_types(
            context
        )

        type_rows = leave_types.get("data") or []


        leave_type = self.leave_service.find_leave_type(
            (
                type_rows
                if isinstance(type_rows, list)
                else []
            ),
            text,
        )


        if not leave_type:

            return {
                "reply": (
                    "نوع درخواست را دقیق‌تر بگویید؛ "
                    "مانند مرخصی ساعتی، استحقاقی "
                    "یا مأموریت ساعتی."
                ),
                "requiresConfirmation": False,
                "data": {
                    "missingField": "requestType",
                },
            }


        is_partial = parse_bool(
            leave_type.get(
                "isAllowedDurationPartialDay"
            )
        )


        if is_partial and len(times) < 2:

            return {
                "reply": (
                    "برای درخواست ساعتی، ساعت "
                    "شروع و پایان لازم است."
                ),
                "requiresConfirmation": False,
            }


        start_date = target_dates[0]

        end_date = (
            target_dates[1]
            if len(target_dates) > 1
            else target_dates[0]
        )


        try:

            start_date, end_date = validate_jalali_range(
                start_date,
                end_date,
            )

            if is_partial:
                hours_between(
                    times[0],
                    times[1],
                )

        except ValueError as exc:

            raise AppError(
                str(exc),
                code="INVALID_LEAVE_RANGE",
            ) from exc


        payload = {

            "absenceTypeCode": (
                leave_type.get(
                    "absenceTypeCode"
                )
            ),

            "startDate": start_date,

            "endDate": end_date,

            "startTime": (
                times[0]
                if is_partial
                else ""
            ),

            "endTime": (
                times[1]
                if is_partial
                else ""
            ),

            "notes": "",

            "additionalValues": self._extract_additional_values(
                text,
                leave_type,
            ),
        }


        existing = await self.leave_service.get_leave_requests(
            context,
            start_date,
        )

        existing_rows = existing.get("data") or []


        action = await self.action_service.create_pending_action(
            str(context.employee_id),
            "CREATE_LEAVE",
            payload,
        )


        warning = (
            " در این بازه درخواست دیگری وجود دارد "
            "و ممکن است هم‌پوشانی ایجاد شود."
            if existing_rows
            else ""
        )


        return {

            "reply": (
                f"ثبت "
                f"{leave_type.get('absenceTypeName') or 'درخواست'} "
                f"برای {start_date} آماده شد."
                f"{warning} تأیید می‌کنید؟"
            ),

            "requiresConfirmation": True,

            "pendingAction": {

                "id": action["id"],

                "label": "تأیید و ثبت درخواست",

                "expiresAt": action.get(
                    "expiresAt"
                ),
            },

            "data": {

                "prepared": payload,

                "existingRequestCount": (
                    len(existing_rows)
                    if isinstance(existing_rows, list)
                    else 0
                ),
            },
        }

    async def delete_leave(
            self,
            context,
            text: str,
            dates: list[str],
    ) -> dict[str, Any]:

        target_date = (
            dates[0]
            if dates
            else context.date
        )

        if not target_date:
            return {
                "reply": (
                    "برای حذف درخواست، تاریخ "
                    "را وارد کنید."
                ),
                "requiresConfirmation": False,
            }

        leave_response = (
            await self.leave_service.get_leave_requests(
                context,
                target_date,
            )
        )

        rows = leave_response.get("data") or []

        if (
                not isinstance(rows, list)
                or not rows
        ):
            return {
                "reply": (
                    "برای این تاریخ درخواستی "
                    "پیدا نشد."
                ),
                "requiresConfirmation": False,
                "data": {
                    "date": target_date,
                },
            }

        leave_types = (
            await self.leave_service.get_leave_types(
                context
            )
        )

        type_rows = leave_types.get("data") or []

        matched = self.leave_service.find_leave_type(
            (
                type_rows
                if isinstance(type_rows, list)
                else []
            ),
            text,
        )

        candidates = rows

        if matched:
            candidates = [
                row
                for row in rows
                if str(
                    row.get(
                        "absenceTypeCode"
                    )
                )
                   == str(
                    matched.get(
                        "absenceTypeCode"
                    )
                )
            ]

        deletable = [
            row
            for row in candidates
            if isinstance(row, dict)
               and parse_bool(
                row.get(
                    "isDeletable"
                )
            )
        ]

        if len(deletable) != 1:
            return {
                "reply": (
                    "یک درخواست قابل حذف و یکتا "
                    "پیدا نشد. ردیف دقیق را از "
                    "پنل درخواست‌ها انتخاب کنید."
                ),
                "requiresConfirmation": False,
                "data": {
                    "candidateCount": len(candidates),
                    "deletableCount": len(deletable),
                },
            }

        row = deletable[0]

        payload = {
            "requestID": row.get(
                "requestID"
            ),
            "changeStateID": row.get(
                "changeStateID"
            ),
            "leaveKey": row.get(
                "leaveKey"
            ),
        }

        if (
                not payload["requestID"]
                or not payload["leaveKey"]
        ):
            raise AppError(
                "اطلاعات درخواست برای حذف کامل نیست.",
                code="INVALID_DELETE_REQUEST",
            )

        action = (
            await self.action_service.create_pending_action(
                str(context.employee_id),
                "DELETE_LEAVE",
                payload,
            )
        )

        return {
            "reply": (
                f"حذف درخواست "
                f"«{row.get('absenceTypeName') or 'درخواست'}» "
                "آماده شد. تأیید می‌کنید؟"
            ),
            "requiresConfirmation": True,
            "pendingAction": {
                "id": action["id"],
                "label": "تأیید و حذف درخواست",
                "expiresAt": action.get(
                    "expiresAt"
                ),
            },
            "data": {
                "requestID": row.get(
                    "requestID"
                ),
                "absenceTypeName": row.get(
                    "absenceTypeName"
                ),
                "status": (
                        row.get("statusTxt")
                        or row.get("statusID")
                ),
            },
        }

    async def list_leaves(
            self,
            context,
            dates: list[str],
    ) -> dict[str, Any]:

        target_date = (
            dates[0]
            if dates
            else str(context.date)
        )

        data = await self.leave_service.get_leave_requests(
            context,
            target_date,
        )

        rows = data.get("data") or []

        return {
            "reply": (
                f"{len(rows) if isinstance(rows, list) else 0} "
                "درخواست برای بازه موردنظر دریافت شد."
            ),
            "requiresConfirmation": False,
            "data": {
                "date": target_date,
                "requests": (
                    rows
                    if isinstance(rows, list)
                    else []
                ),
            },
        }

    async def list_leaves(
            self,
            context,
            dates: list[str],
    ) -> dict[str, Any]:

        target_date = (
            dates[0]
            if dates
            else str(context.date)
        )

        data = await self.leave_service.get_leave_requests(
            context,
            target_date,
        )

        rows = data.get("data") or []

        return {
            "reply": (
                f"{len(rows) if isinstance(rows, list) else 0} "
                "درخواست برای بازه موردنظر دریافت شد."
            ),
            "requiresConfirmation": False,
            "data": {
                "date": target_date,
                "requests": (
                    rows
                    if isinstance(rows, list)
                    else []
                ),
            },
        }

    async def handle(
        self,
        context,
        text: str,
        dates: list[str],
        times: list[str],
    ) -> dict[str, Any]:

        if self.is_balance_request(text):

            target_date = (
                dates[0]
                if dates
                else str(context.date)
            )

            return await self.get_balance(
                context,
                target_date,
            )


        if self.can_create(text):

            return await self.create_leave(
                context,
                text,
                dates,
                times,
            )


        return {
            "reply": (
                "Leave handler آماده انتقال منطق است."
            ),
            "requiresConfirmation": False,
        }