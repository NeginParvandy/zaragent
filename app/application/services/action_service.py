from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any
from uuid import uuid4

from app.application.services.food_service import FoodService
from app.application.services.hr_service import HrService
from app.core.config import Settings
from app.core.time import local_jalali_today
from app.core.exceptions import (
    AppError,
    ConflictError,
    IntegrationError,
    NotFoundError,
)
from app.domain.models import AgentContext, PendingActionRecord
from app.domain.text import parse_int
from app.infrastructure.repositories.state_repository import StateRepository

logger = logging.getLogger(__name__)

UNCERTAIN_INTEGRATION_CODES = {
    "DOWNSTREAM_UNAVAILABLE",
    "DOWNSTREAM_TIMEOUT",
    "DOWNSTREAM_HTTP_ERROR",
    "DOWNSTREAM_INVALID_CONTENT",
    "DOWNSTREAM_INVALID_JSON",
    "DOWNSTREAM_CIRCUIT_OPEN",
}

DEFAULT_FOOD_MEAL_ID = 1


class ActionService:
    def __init__(
        self,
        settings: Settings,
        repository: StateRepository,
        food: FoodService,
        hr: HrService,
    ):
        self.settings = settings
        self.repository = repository
        self.food = food
        self.hr = hr

    # ATTENDANCE_FUTURE_ACTION_GUARD_V1
    @staticmethod
    def _attendance_ascii_digits(
        value: Any,
    ) -> str:
        return str(
            value
            or ""
        ).translate(
            str.maketrans(
                "۰۱۲۳۴۵۶۷۸۹",
                "0123456789",
            )
        ).strip()

    @classmethod
    def _attendance_date_key(
        cls,
        value: Any,
    ) -> tuple[
        int,
        int,
        int,
    ] | None:
        normalized = (
            cls._attendance_ascii_digits(
                value
            )
            .replace("-", "/")
            .replace(".", "/")
        )

        match = re.fullmatch(
            (
                r"\s*"
                r"([0-9]{4})"
                r"/"
                r"([0-9]{1,2})"
                r"/"
                r"([0-9]{1,2})"
                r"\s*"
            ),
            normalized,
        )

        if not match:
            return None

        year = int(
            match.group(1)
        )

        month = int(
            match.group(2)
        )

        day = int(
            match.group(3)
        )

        if not 1 <= month <= 12:
            return None

        if not 1 <= day <= 31:
            return None

        return (
            year,
            month,
            day,
        )

    @classmethod
    def _attendance_time_key(
        cls,
        value: Any,
    ) -> tuple[
        int,
        int,
    ] | None:
        normalized = (
            cls._attendance_ascii_digits(
                value
            )
        )

        match = re.fullmatch(
            (
                r"\s*"
                r"([0-9]{1,2})"
                r":"
                r"([0-9]{2})"
                r"(?:"
                r":"
                r"[0-9]{2}"
                r")?"
                r"\s*"
            ),
            normalized,
        )

        if not match:
            return None

        hour = int(
            match.group(1)
        )

        minute = int(
            match.group(2)
        )

        if not 0 <= hour <= 23:
            return None

        if not 0 <= minute <= 59:
            return None

        return (
            hour,
            minute,
        )

    def attendance_future_reason(
        self,
        event_date: Any,
        event_time: Any = None,
        *,
        today: Any = None,
        now_time: (
            str
            | tuple[int, int]
            | None
        ) = None,
    ) -> str | None:
        timezone_name = str(
            getattr(
                self.settings,
                "app_timezone",
                "Asia/Tehran",
            )
            or "Asia/Tehran"
        )

        today_value = (
            str(today)
            if today is not None
            else local_jalali_today(
                timezone_name
            )
        )

        event_date_key = (
            self._attendance_date_key(
                event_date
            )
        )

        today_key = (
            self._attendance_date_key(
                today_value
            )
        )

        if (
            event_date_key is None
            or today_key is None
        ):
            return None

        if event_date_key > today_key:
            return "future_date"

        if event_date_key < today_key:
            return None

        event_time_key = (
            self._attendance_time_key(
                event_time
            )
        )

        if event_time_key is None:
            return None

        if isinstance(
            now_time,
            tuple,
        ):
            current_time_key = (
                int(now_time[0]),
                int(now_time[1]),
            )

        elif now_time is not None:
            current_time_key = (
                self._attendance_time_key(
                    now_time
                )
            )

            if current_time_key is None:
                return None

        else:
            try:
                current = datetime.now(
                    ZoneInfo(
                        timezone_name
                    )
                )

            except Exception:
                current = (
                    datetime.now()
                    .astimezone()
                )

            current_time_key = (
                current.hour,
                current.minute,
            )

        if (
            event_time_key
            > current_time_key
        ):
            return "future_time"

        return None

    def _ensure_attendance_not_future(
        self,
        action_type: str,
        payload: dict[str, Any],
        *,
        today: Any = None,
        now_time: (
            str
            | tuple[int, int]
            | None
        ) = None,
    ) -> None:
        if action_type != "CREATE_TIME_EVENT":
            return

        reason = (
            self.attendance_future_reason(
                payload.get(
                    "eventDate"
                ),
                payload.get(
                    "eventTime"
                ),
                today=today,
                now_time=now_time,
            )
        )

        if reason is None:
            return

        raise AppError(
            (
                "ثبت تردد برای زمان آینده "
                "امکان‌پذیر نیست. لطفاً تاریخ "
                "و ساعت گذشته یا زمان فعلی "
                "را اعلام کنید."
            ),
            status_code=409,
            code=(
                "FUTURE_ATTENDANCE_NOT_ALLOWED"
            ),
            details={
                "reason": reason,
                "eventDate": payload.get(
                    "eventDate"
                ),
                "eventTime": payload.get(
                    "eventTime"
                ),
            },
        )

    def new_pending_action_record(
        self,
        employee_id: str,
        action_type: str,
        payload: dict[str, Any],
        *,
        reminder_id: str | None = None,
    ) -> PendingActionRecord:
        now = datetime.now(tz=timezone.utc)
        action_id = uuid4().hex

        return PendingActionRecord(
            id=action_id,
            employee_id=employee_id,
            action_type=action_type,
            payload=payload,
            status="pending",
            created_at=now,
            updated_at=now,
            expires_at=now
            + timedelta(
                minutes=self.settings.pending_action_expire_minutes
            ),
            idempotency_key=hashlib.sha256(
                f"{employee_id}:{action_id}:{action_type}".encode()
            ).hexdigest(),
            reminder_id=reminder_id,
        )

    async def create_pending_action(
        self,
        employee_id: str,
        action_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self._validate_payload(
            action_type,
            payload,
        )

        self._ensure_attendance_not_future(
            action_type,
            payload,
        )

        record = self.new_pending_action_record(
            employee_id,
            action_type,
            payload,
        )

        dedup_key = hashlib.sha256(
            (
                f"{employee_id}:{action_type}:"
                f"{json.dumps(payload, sort_keys=True, ensure_ascii=False)}"
            ).encode()
        ).hexdigest()

        saved = await asyncio.to_thread(
            self.repository.save_pending_action,
            record,
            dedup_key,
        )

        return {
            "id": saved.id,
            "type": saved.action_type,
            "expiresAt": (
                saved.expires_at.isoformat()
                if saved.expires_at
                else None
            ),
        }

    async def status(
        self,
        context: AgentContext,
        action_id: str,
    ) -> dict[str, Any]:
        employee_id = str(
            context.employee_id or ""
        )

        state = await asyncio.to_thread(
            self.repository.get_action_state,
            action_id,
            employee_id,
        )

        if not state:
            raise NotFoundError(
                "عملیات پیدا نشد یا متعلق به این کاربر نیست."
            )

        return state

    async def confirm(
        self,
        context: AgentContext,
        action_id: str,
    ) -> dict[str, Any]:
        employee_id = str(
            context.employee_id or ""
        )

        record = await asyncio.to_thread(
            self.repository.claim_pending_action,
            action_id,
            employee_id,
        )

        if not record:
            current = await asyncio.to_thread(
                self.repository.get_pending_action,
                action_id,
                employee_id or None,
            )

            if not current:
                raise NotFoundError(
                    "عملیات در انتظار پیدا نشد یا متعلق به این کاربر نیست."
                )

            if current.status == "expired":
                raise ConflictError(
                    "مهلت تأیید این عملیات تمام شده است.",
                    details={
                        "status": current.status,
                    },
                )

            raise ConflictError(
                "این عملیات قبلاً پردازش یا در حال پردازش است.",
                details={
                    "status": current.status,
                },
            )

        try:
            self._validate_payload(
                record.action_type,
                record.payload,
            )

            result = await self._execute(
                context,
                record.action_type,
                record.payload,
                record.idempotency_key,
            )

        except IntegrationError as exc:
            final_status = (
                "unknown"
                if exc.code in UNCERTAIN_INTEGRATION_CODES
                else "failed"
            )

            await asyncio.to_thread(
                self.repository.complete_pending_action,
                action_id,
                final_status,
                error_message=exc.code,
            )

            if final_status == "unknown":
                raise AppError(
                    (
                        "نتیجه عملیات به دلیل قطع یا پاسخ نامعتبر "
                        "سرویس مقصد مشخص نیست. دوباره تأیید نکنید "
                        "و وضعیت را بررسی کنید."
                    ),
                    status_code=409,
                    code="ACTION_RESULT_UNKNOWN",
                    details={
                        "actionId": action_id,
                        "sourceCode": exc.code,
                    },
                ) from exc

            raise

        except AppError as exc:
            await asyncio.to_thread(
                self.repository.complete_pending_action,
                action_id,
                "failed",
                error_message=exc.code,
            )
            raise

        except Exception as exc:
            logger.exception(
                "Unexpected action execution failure action_id=%s",
                action_id,
            )

            await asyncio.to_thread(
                self.repository.complete_pending_action,
                action_id,
                "unknown",
                error_message=type(exc).__name__,
            )

            raise AppError(
                (
                    "وضعیت نتیجه عملیات نامطمئن است. عملیات را "
                    "دوباره اجرا نکنید و وضعیت را بررسی کنید."
                ),
                status_code=500,
                code="ACTION_RESULT_UNKNOWN",
                details={
                    "actionId": action_id,
                },
            ) from exc

        try:
            completed = await asyncio.to_thread(
                self.repository.complete_pending_action,
                action_id,
                "succeeded",
                result=result,
            )

        except Exception as exc:
            logger.critical(
                "Action completion persistence failed action_id=%s",
                action_id,
                exc_info=True,
            )

            try:
                await asyncio.to_thread(
                    self.repository.complete_pending_action,
                    action_id,
                    "unknown",
                    error_message=type(exc).__name__,
                )
            except Exception:
                logger.exception(
                    "Could not mark action unknown action_id=%s",
                    action_id,
                )

            raise AppError(
                (
                    "عملیات اجرا شد اما ثبت نتیجه نهایی نامطمئن "
                    "است. عملیات را دوباره اجرا نکنید."
                ),
                status_code=500,
                code="ACTION_RESULT_UNKNOWN",
                details={
                    "actionId": action_id,
                },
            ) from exc

        if not completed:
            persisted_state = await asyncio.to_thread(
                self.repository.get_action_state,
                action_id,
                employee_id,
            )

            if (
                persisted_state
                and persisted_state.get("status") == "succeeded"
            ):
                return persisted_state

            await asyncio.to_thread(
                self.repository.complete_pending_action,
                action_id,
                "unknown",
                error_message="RESULT_PERSISTENCE_CONFLICT",
            )

            raise AppError(
                (
                    "عملیات اجرا شد اما وضعیت نهایی نامطمئن است. "
                    "عملیات را دوباره اجرا نکنید."
                ),
                status_code=500,
                code="ACTION_RESULT_UNKNOWN",
                details={
                    "actionId": action_id,
                },
            )

        return {
            "actionId": action_id,
            "actionType": record.action_type,
            "status": "succeeded",
            "result": result,
        }

    async def cancel(
        self,
        context: AgentContext,
        action_id: str,
    ) -> dict[str, Any]:
        employee_id = str(
            context.employee_id or ""
        ).strip()

        if not employee_id:
            raise AppError(
                "کد پرسنلی کاربر مشخص نیست.",
                code="MISSING_EMPLOYEE_ID",
            )

        current = await asyncio.to_thread(
            self.repository.get_pending_action,
            action_id,
            employee_id,
        )

        if not current:
            raise NotFoundError(
                "عملیات پیدا نشد یا متعلق به این کاربر نیست."
            )

        if current.status == "pending":
            cancelled = await asyncio.to_thread(
                self.repository.cancel_pending_action,
                action_id,
                employee_id,
            )

            if cancelled:
                return {
                    "actionId": action_id,
                    "actionType": current.action_type,
                    "cancelled": True,
                    "canCancel": False,
                    "currentStatus": "cancelled",
                    "blockedBy": None,
                    "reasonCode": None,
                    "nextAction": None,
                    "message": "عملیات با موفقیت لغو شد.",
                }

            # ممکن است بین خواندن وضعیت و اجرای لغو،
            # پردازش دیگری وضعیت عملیات را تغییر داده باشد.
            current = await asyncio.to_thread(
                self.repository.get_pending_action,
                action_id,
                employee_id,
            )

            if not current:
                raise NotFoundError(
                    "عملیات پیدا نشد یا متعلق به این کاربر نیست."
                )

        if current.status == "succeeded":
            succeeded_guidance: dict[
                str,
                dict[str, Any],
            ] = {
                "CREATE_LEAVE": {
                    "nextAction": "DELETE_LEAVE",
                    "message": (
                        "این درخواست مرخصی قبلاً با موفقیت ثبت شده است "
                        "و دیگر از این مرحله قابل لغو نیست. "
                        "برای لغو مرخصی، درخواست حذف مرخصی را ثبت کنید."
                    ),
                },
                "RESERVE_FOOD": {
                    "nextAction": "CANCEL_FOOD",
                    "message": (
                        "رزرو غذا قبلاً با موفقیت انجام شده است. "
                        "برای لغو آن، از گزینه لغو رزرو غذا استفاده کنید."
                    ),
                },
                "CREATE_TIME_EVENT": {
                    "nextAction": None,
                    "message": (
                        "این تردد قبلاً ثبت شده است و از این بخش "
                        "امکان لغو آن وجود ندارد."
                    ),
                },
                "DELETE_LEAVE": {
                    "nextAction": None,
                    "message": (
                        "درخواست حذف مرخصی قبلاً با موفقیت انجام شده است "
                        "و نیازی به لغو دوباره ندارد."
                    ),
                },
                "CANCEL_FOOD": {
                    "nextAction": None,
                    "message": (
                        "لغو رزرو غذا قبلاً با موفقیت انجام شده است "
                        "و نیازی به لغو دوباره ندارد."
                    ),
                },
                "RATE_FOOD": {
                    "nextAction": None,
                    "message": (
                        "امتیاز غذا قبلاً ثبت شده است و این عملیات "
                        "دیگر قابل لغو نیست."
                    ),
                },
            }

            guidance = succeeded_guidance.get(
                current.action_type,
                {
                    "nextAction": None,
                    "message": (
                        "این عملیات قبلاً با موفقیت انجام شده است "
                        "و دیگر از این مرحله قابل لغو نیست."
                    ),
                },
            )

            return {
                "actionId": action_id,
                "actionType": current.action_type,
                "cancelled": False,
                "canCancel": False,
                "currentStatus": current.status,
                "blockedBy": "status",
                "reasonCode": "ACTION_ALREADY_SUCCEEDED",
                "nextAction": guidance["nextAction"],
                "message": guidance["message"],
            }

        status_guidance: dict[
            str,
            dict[str, str],
        ] = {
            "processing": {
                "reasonCode": "ACTION_PROCESSING",
                "message": (
                    "این عملیات در حال پردازش است و فعلاً امکان لغو آن "
                    "وجود ندارد. کمی بعد وضعیت آن را بررسی کنید."
                ),
            },
            "cancelled": {
                "reasonCode": "ACTION_ALREADY_CANCELLED",
                "message": "این عملیات قبلاً لغو شده است.",
            },
            "expired": {
                "reasonCode": "ACTION_EXPIRED",
                "message": (
                    "مهلت این عملیات تمام شده است و دیگر قابل لغو نیست."
                ),
            },
            "failed": {
                "reasonCode": "ACTION_FAILED",
                "message": (
                    "این عملیات قبلاً ناموفق شده است و نیازی به لغو ندارد."
                ),
            },
            "unknown": {
                "reasonCode": "ACTION_RESULT_UNKNOWN",
                "message": (
                    "نتیجه این عملیات مشخص نیست. برای جلوگیری از انجام "
                    "تکراری، امکان لغو آن وجود ندارد و باید وضعیت آن بررسی شود."
                ),
            },
        }

        guidance = status_guidance.get(
            current.status,
            {
                "reasonCode": "ACTION_NOT_CANCELLABLE",
                "message": (
                    f"این عملیات در وضعیت «{current.status}» قرار دارد "
                    "و قابل لغو نیست."
                ),
            },
        )

        return {
            "actionId": action_id,
            "actionType": current.action_type,
            "cancelled": False,
            "canCancel": False,
            "currentStatus": current.status,
            "blockedBy": "status",
            "reasonCode": guidance["reasonCode"],
            "nextAction": None,
            "message": guidance["message"],
        }

    async def _execute(
        self,
        context: AgentContext,
        action_type: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._ensure_attendance_not_future(
            action_type,
            payload,
        )

        if action_type == "RESERVE_FOOD":
            food_context = self._food_context_from_payload(
                context,
                payload,
            )

            return await self.food.reserve_food(
                food_context,
                payload["planDetailId"],
                idempotency_key=idempotency_key,
            )

        if action_type == "CANCEL_FOOD":
            food_context = self._food_context_from_payload(
                context,
                payload,
            )

            return await self.food.cancel_food(
                food_context,
                payload["planDetailId"],
                idempotency_key=idempotency_key,
            )

        # FOOD_CHANGE_ACTION_FINAL_V1
        if action_type == "CHANGE_FOOD":
            food_context = self._food_context_from_payload(
                context,
                payload,
            )

            old_plan_id = parse_int(
                payload.get(
                    "oldPlanDetailId"
                )
            )

            new_plan_id = parse_int(
                payload.get(
                    "newPlanDetailId"
                )
            )

            if (
                old_plan_id is None
                or old_plan_id == 0
            ):
                raise AppError(
                    "شناسه رزرو فعلی معتبر نیست.",
                    code="INVALID_OLD_PLAN_DETAIL",
                )

            if (
                new_plan_id is None
                or new_plan_id == 0
            ):
                raise AppError(
                    "شناسه غذای جایگزین معتبر نیست.",
                    code="INVALID_NEW_PLAN_DETAIL",
                )

            if old_plan_id == new_plan_id:
                raise AppError(
                    "غذای فعلی و غذای جایگزین یکسان هستند.",
                    code="SAME_FOOD_REPLACEMENT",
                )

            cancel_result = (
                await self.food.cancel_food(
                    food_context,
                    old_plan_id,
                    idempotency_key=(
                        f"{idempotency_key}:cancel"
                    ),
                )
            )

            try:
                reserve_result = (
                    await self.food.reserve_food(
                        food_context,
                        new_plan_id,
                        idempotency_key=(
                            f"{idempotency_key}:reserve"
                        ),
                    )
                )

            except IntegrationError as exc:
                if (
                    exc.code
                    in UNCERTAIN_INTEGRATION_CODES
                ):
                    # The new reservation may have reached
                    # the downstream service. Do not attempt
                    # an unsafe automatic rollback.
                    raise

                reserve_error = exc

            except Exception as exc:
                reserve_error = exc

            else:
                return {
                    "changed": True,
                    "targetDate": payload.get(
                        "targetDate"
                    ),
                    "oldFoodName": payload.get(
                        "oldFoodName"
                    ),
                    "newFoodName": payload.get(
                        "newFoodName"
                    ),
                    "oldPlanDetailId": (
                        old_plan_id
                    ),
                    "newPlanDetailId": (
                        new_plan_id
                    ),
                    "cancelResult": (
                        cancel_result
                    ),
                    "reserveResult": (
                        reserve_result
                    ),
                }

            try:
                rollback_result = (
                    await self.food.reserve_food(
                        food_context,
                        old_plan_id,
                        idempotency_key=(
                            f"{idempotency_key}:rollback"
                        ),
                    )
                )

            except Exception as rollback_exc:
                raise AppError(
                    (
                        "رزرو قبلی لغو شد، اما رزرو "
                        "غذای جدید و بازگردانی رزرو "
                        "قبلی هر دو ناموفق بودند. "
                        "وضعیت رزرو را بررسی کنید."
                    ),
                    status_code=409,
                    code=(
                        "FOOD_CHANGE_PARTIAL_FAILURE"
                    ),
                    details={
                        "targetDate": payload.get(
                            "targetDate"
                        ),
                        "oldFoodName": payload.get(
                            "oldFoodName"
                        ),
                        "newFoodName": payload.get(
                            "newFoodName"
                        ),
                        "reserveError": (
                            type(
                                reserve_error
                            ).__name__
                        ),
                        "rollbackError": (
                            type(
                                rollback_exc
                            ).__name__
                        ),
                    },
                ) from reserve_error

            raise AppError(
                (
                    "رزرو غذای جدید انجام نشد؛ "
                    "رزرو قبلی با موفقیت بازگردانده شد."
                ),
                status_code=409,
                code="FOOD_CHANGE_ROLLED_BACK",
                details={
                    "targetDate": payload.get(
                        "targetDate"
                    ),
                    "oldFoodName": payload.get(
                        "oldFoodName"
                    ),
                    "newFoodName": payload.get(
                        "newFoodName"
                    ),
                    "rollbackResult": (
                        rollback_result
                    ),
                },
            ) from reserve_error

        if action_type == "RATE_FOOD":
            return await self.food.set_rating(
                context,
                reserve_id=payload["reserveId"],
                rate=payload["rate"],
                comment=payload.get("comment") or "",
                is_anonymous=payload.get(
                    "isAnonymous",
                    False,
                ),
                idempotency_key=idempotency_key,
            )

        if action_type == "DELETE_LEAVE":
            return await self.hr.delete_leave_request(
                context,
                str(payload["requestID"]),
                payload.get("changeStateID") or 0,
                str(payload["leaveKey"]),
                idempotency_key=idempotency_key,
            )

        if action_type == "CREATE_TIME_EVENT":
            events = await self.hr.get_time_events(
                context,
                payload["eventDate"],
                payload["eventDate"],
            )

            valid, existing = (
                self.hr.validate_time_event_distance(
                    events.get("data") or [],
                    payload["eventTime"],
                )
            )

            if not valid:
                raise ConflictError(
                    "تردد مشابه قبلاً ثبت شده است.",
                    details={
                        "existingTime": existing,
                    },
                )

            return await self.hr.post_time_event(
                context,
                payload["eventDate"],
                payload["eventTime"],
                payload.get("note") or "",
                idempotency_key=idempotency_key,
            )

        if action_type == "CREATE_LEAVE":
            leave_types = await self.hr.get_leave_types(
                context
            )
            rows = leave_types.get("data") or []

            leave_type = next(
                (
                    item
                    for item in rows
                    if str(
                        item.get("absenceTypeCode")
                    )
                    == str(
                        payload.get("absenceTypeCode")
                    )
                ),
                None,
            )

            if not leave_type:
                raise AppError(
                    "نوع درخواست در API HR پیدا نشد.",
                    details={
                        "absenceTypeCode": payload.get(
                            "absenceTypeCode"
                        ),
                    },
                )

            await self.hr.ensure_no_exact_duplicate_leave(
                context,
                absence_type_code=str(
                    payload.get("absenceTypeCode") or ""
                ),
                start_date=payload["startDate"],
                end_date=(
                    payload.get("endDate")
                    or payload["startDate"]
                ),
                start_time=(
                    payload.get("startTime") or ""
                ),
                end_time=(
                    payload.get("endTime") or ""
                ),
            )

            return await self.hr.save_leave(
                context,
                leave_type,
                start_date=payload["startDate"],
                end_date=(
                    payload.get("endDate")
                    or payload["startDate"]
                ),
                start_time=(
                    payload.get("startTime") or ""
                ),
                end_time=(
                    payload.get("endTime") or ""
                ),
                notes=payload.get("notes") or "",
                additional_values=(
                    payload.get("additionalValues")
                    or {}
                ),
                idempotency_key=idempotency_key,
            )

        raise AppError(
            "نوع عملیات پشتیبانی نمی‌شود.",
            details={
                "actionType": action_type,
            },
        )

    @staticmethod
    def _food_context_from_payload(
        context: AgentContext,
        payload: dict[str, Any],
    ) -> AgentContext:
        restaurant_id = parse_int(
            payload.get("restaurantId")
        )

        if restaurant_id is None:
            restaurant_id = parse_int(
                getattr(
                    context,
                    "restaurant_id",
                    None,
                )
            )

        meal_id = parse_int(
            payload.get("mealId")
        )

        if meal_id is None:
            meal_id = parse_int(
                getattr(
                    context,
                    "meal_id",
                    None,
                )
            )

        if meal_id is None:
            meal_id = DEFAULT_FOOD_MEAL_ID

        if (
            restaurant_id is None
            or restaurant_id <= 0
        ):
            raise AppError(
                (
                    "رستوران عملیات غذا مشخص نیست. "
                    "درخواست غذا را دوباره از چت شروع کنید."
                ),
                code="MISSING_RESTAURANT_ID",
            )

        if meal_id <= 0:
            raise AppError(
                "شناسه وعده غذایی معتبر نیست.",
                code="INVALID_MEAL_ID",
            )

        return context.model_copy(
            update={
                "restaurant_id": restaurant_id,
                "meal_id": meal_id,
            }
        )

    @staticmethod
    def _validate_payload(
        action_type: str,
        payload: dict[str, Any],
    ) -> None:
        required: dict[
            str,
            tuple[str, ...],
        ] = {
            "RESERVE_FOOD": (
                "planDetailId",
            ),
            "CANCEL_FOOD": (
                "planDetailId",
            ),
            "CHANGE_FOOD": (
                "oldPlanDetailId",
                "newPlanDetailId",
            ),
            "RATE_FOOD": (
                "reserveId",
                "rate",
            ),
            "DELETE_LEAVE": (
                "requestID",
                "leaveKey",
            ),
            "CREATE_TIME_EVENT": (
                "eventDate",
                "eventTime",
            ),
            "CREATE_LEAVE": (
                "absenceTypeCode",
                "startDate",
            ),
        }

        fields = required.get(
            action_type
        )

        if fields is None:
            raise AppError(
                "نوع عملیات پشتیبانی نمی‌شود.",
                code="UNSUPPORTED_ACTION",
                details={
                    "actionType": action_type,
                },
            )

        missing = [
            field
            for field in fields
            if payload.get(field) in (
                None,
                "",
            )
        ]

        if missing:
            raise AppError(
                "اطلاعات عملیات کامل نیست.",
                code="INVALID_ACTION_PAYLOAD",
                details={
                    "missing": missing,
                },
            )