from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from app.application.services.action_service import ActionService
from app.application.services.daily_brief_service import DailyBriefService
from app.application.services.food_service import FoodService
from app.application.services.hr_service import HrService
from app.application.services.leave_balance_formatter import format_leave_balance_reply
from app.application.services.intent_guard import IntentGuard
from app.application.services.nlu_core import (
    analyze_message,
    normalize_text as normalize_nlu_text,
)
from app.core.exceptions import AppError
from app.domain.models import AgentContext
from app.domain.text import (
    extract_jalali_dates,
    extract_times,
    hours_between,
    normalize_persian_text,
    parse_bool,
    parse_int,
    validate_jalali_range,
)
from app.infrastructure.repositories.state_repository import StateRepository


FOOD_RESTAURANT_CONFIRM_STATE = "food_restaurant_confirmation"
FOOD_RESTAURANT_SELECT_STATE = "food_restaurant_selection"
FOOD_CHAT_STATE_TTL_MINUTES = 3
CONVERSATION_STATE = "conversation"
CONVERSATION_STATE_TTL_MINUTES = 3

# CONFIRM_REPLAY_CACHE_V1
CONFIRM_REPLAY_TTL_SECONDS = 20
CONFIRM_REPLAY_WAIT_SECONDS = 5

FOOD_MEAL_ID = 1


class ChatService:
    def __init__(
        self,
        food: FoodService,
        hr: HrService,
        actions: ActionService,
        daily_brief: DailyBriefService,
        repository: StateRepository,
    ):
        self.food = food
        self.hr = hr
        self.actions = actions
        self.daily_brief = daily_brief
        self.repository = repository
        self.intent_guard = IntentGuard()

    async def handle(
        self,
        context: AgentContext,
        message: str,
    ) -> dict[str, Any]:
        # CHAT_CONTEXT_TIME_FINAL_V1
        text = normalize_nlu_text(
            normalize_persian_text(
                message
            )
        )

        pending_state_response = (
            await self._handle_pending_chat_state(
                context,
                text,
            )
        )

        if pending_state_response is not None:
            return pending_state_response

        conversation_payload = (
            await self._load_conversation_payload(
                context
            )
        )

        context, selected_restaurant = (
            self._apply_saved_restaurant(
                context,
                conversation_payload,
            )
        )

        control_response = (
            await self._handle_pending_action_reply(
                context,
                text,
                conversation_payload,
            )
        )

        if control_response is not None:
            return control_response

        # FOOD_CANCEL_CHANGE_FINAL_V1
        food_mutation_response = (
            await self._handle_explicit_food_mutation(
                context,
                text,
                conversation_payload,
                selected_restaurant,
            )
        )

        if food_mutation_response is not None:
            return food_mutation_response

        # ACTIVE_CONTEXT_ANALYSIS_V1
        # When a conversation is waiting for a missing field,
        # analyze the user's reply together with the previous
        # request. Explicit cancellation and explicit new
        # requests must remain independent.
        contextual_analysis_message = message
        contextual_analysis_text = text

        active_nlu_state = (
            conversation_payload.get(
                "nluState"
            )
            if isinstance(
                conversation_payload.get(
                    "nluState"
                ),
                dict,
            )
            else {}
        )

        active_missing_fields = (
            active_nlu_state.get(
                "missingFields"
            )
            if isinstance(
                active_nlu_state.get(
                    "missingFields"
                ),
                list,
            )
            else []
        )

        active_original_message = str(
            conversation_payload.get(
                "originalMessage"
            )
            or ""
        ).strip()

        conversation_cancel_terms = {
            "لغو",
            "لغوش کن",
            "لغو کن",
            "کنسل",
            "کنسل کن",
            "بیخیال",
            "بی خیال",
        }

        if (
            active_missing_fields
            and text in conversation_cancel_terms
        ):
            await self._delete_conversation_state(
                context
            )

            return {
                "reply": (
                    "باشه، درخواست نیمه‌کاره لغو شد."
                ),
                "requiresConfirmation": False,
                "data": {
                    "conversationCancelled": True,
                },
            }

        should_use_active_context = (
            bool(active_missing_fields)
            and bool(active_original_message)
            and text
            not in conversation_cancel_terms
            and not self._looks_like_new_request(
                text
            )
        )

        if should_use_active_context:
            contextual_analysis_message = (
                f"{active_original_message} {text}"
            ).strip()

            contextual_analysis_text = (
                normalize_nlu_text(
                    normalize_persian_text(
                        contextual_analysis_message
                    )
                )
            )

        # FOOD_FINAL_PART1_ORDER_V1
        intent_decision = self.intent_guard.analyze(
            contextual_analysis_text
        )

        if not intent_decision.allowed:
            guard_payload = (
                await self._load_conversation_payload(
                    context
                )
            )

            if not self._is_contextual_guard_continuation(
                text,
                guard_payload,
            ):
                return intent_decision.to_response()

        if self._is_help(text):
            return self._help_response()

        if self._is_daily_brief(text):
            data = await self.daily_brief.build(
                context
            )

            return {
                "reply": (
                    data.get("summary")
                    or "گزارش روزانه آماده شد."
                ),
                "requiresConfirmation": False,
                "data": data,
            }

        if self._is_greeting(text):
            name = (
                f" {context.display_name}"
                if context.display_name
                else ""
            )

            return {
                "reply": (
                    f"سلام{name}. آماده‌ام امور غذا، مرخصی، "
                    "مأموریت و تردد را برایت بررسی کنم."
                ),
                "requiresConfirmation": False,
                "suggestions": self._suggestions(),
            }

        reference_date = str(
            context.date or ""
        ).strip()

        previous_nlu_state = (
            conversation_payload.get(
                "nluState"
            )
            if isinstance(
                conversation_payload.get(
                    "nluState"
                ),
                dict,
            )
            else None
        )

        previous_nlu_state = (
            self._nlu_state_with_active_date(
                previous_nlu_state,
                conversation_payload,
            )
        )

        nlu_result = analyze_message(
            contextual_analysis_message,
            reference_date=reference_date,
            conversation_state=(
                previous_nlu_state
            ),
        )

        nlu_result = (
            self._enrich_food_nlu_result(
                nlu_result,
                text,
                conversation_payload,
            )
        )

        future_attendance_response = (
            await self._handle_future_attendance_guard(
                context,
                nlu_result,
            )
        )

        if future_attendance_response is not None:
            return future_attendance_response

        await self._cancel_pending_on_domain_switch(
            context,
            conversation_payload,
            nlu_result,
        )

        combined_text = (
            self._combined_conversation_text(
                text,
                conversation_payload,
                nlu_result,
            )
        )

        # FOOD_ROUTER_V4
        nlu_result = (
            self._override_explicit_food_command(
                nlu_result,
                combined_text,
                conversation_payload,
            )
        )

        if nlu_result.get(
            "needsClarification"
        ):
            updated_payload = dict(
                conversation_payload
            )
            updated_payload.update(
                {
                    "nluState": (
                        nlu_result.get("state")
                        or {}
                    ),
                    "originalMessage": (
                        combined_text
                    ),
                    "lastDomain": (
                        nlu_result.get("domain")
                    ),
                }
            )
            updated_payload.pop(
                "pendingActionId",
                None,
            )
            updated_payload.pop(
                "proposal",
                None,
            )

            await self._save_conversation_payload(
                context,
                updated_payload,
            )

            return {
                "reply": (
                    nlu_result.get(
                        "clarification"
                    )
                    or (
                        "لطفاً جزئیات بیشتری "
                        "بفرمایید."
                    )
                ),
                "requiresConfirmation": False,
                "data": {
                    "domain": (
                        nlu_result.get("domain")
                    ),
                    "intent": (
                        nlu_result.get("intent")
                    ),
                    "missingFields": (
                        nlu_result.get(
                            "missingFields"
                        )
                        or []
                    ),
                },
            }

        entities = (
            nlu_result.get("entities")
            if isinstance(
                nlu_result.get("entities"),
                dict,
            )
            else {}
        )

        dates = self._dates_from_entities(
            entities
        )
        times = self._times_from_entities(
            entities
        )

        intent = str(
            nlu_result.get("intent")
            or ""
        )
        domain = str(
            nlu_result.get("domain")
            or ""
        )

        try:
            if intent in {
                "SHOW_FOOD_MENU",
                "SHOW_FOOD_RESERVATION",
                "RESERVE_FOOD",
                "CANCEL_FOOD",
                "FOOD_UNKNOWN",
            } or (
                domain == "FOOD"
                and self._is_food(text)
            ):
                response = await self._handle_food(
                    context,
                    combined_text,
                    dates,
                    restaurant_validated=(
                        context.restaurant_id
                        is not None
                    ),
                    selected_restaurant=(
                        selected_restaurant
                    ),
                    conversation_payload=(
                        conversation_payload
                    ),
                )

                return await self._finalize_response_state(
                    context,
                    nlu_result,
                    conversation_payload,
                    response,
                    combined_text,
                )

            if intent == "GET_LEAVE_BALANCE":
                target_date = (
                    dates[0]
                    if dates
                    else str(context.date)
                )

                data = await self.hr.get_time_account(
                    context,
                    target_date,
                )

                rows = data.get("data", data)

                response = {
                    "reply": (
                        format_leave_balance_reply(
                            rows
                        )
                    ),
                    "requiresConfirmation": False,
                    "data": rows,
                }

                return await self._finalize_response_state(
                    context,
                    nlu_result,
                    conversation_payload,
                    response,
                    combined_text,
                )

            if intent == "SHOW_LEAVE_REQUESTS":
                target_date = (
                    dates[0]
                    if dates
                    else str(context.date)
                )

                data = (
                    await self.hr.get_leave_requests(
                        context,
                        target_date,
                    )
                )
                rows = data.get("data") or []

                response = {
                    "reply": (
                        f"{len(rows) if isinstance(rows, list) else 0} "
                        "درخواست برای بازه موردنظر دریافت شد."
                    ),
                    "requiresConfirmation": False,
                    "data": {
                        "date": target_date,
                        "requests": (
                            rows
                            if isinstance(
                                rows,
                                list,
                            )
                            else []
                        ),
                    },
                }

                return await self._finalize_response_state(
                    context,
                    nlu_result,
                    conversation_payload,
                    response,
                    combined_text,
                )

            if intent in {
                "CANCEL_LEAVE",
                "CANCEL_MISSION",
            }:
                response = (
                    await self._prepare_delete_leave(
                        context,
                        combined_text,
                        dates,
                    )
                )

                return await self._finalize_response_state(
                    context,
                    nlu_result,
                    conversation_payload,
                    response,
                    combined_text,
                )

            if intent in {
                "CREATE_LEAVE",
                "CREATE_MISSION",
            }:
                # LEAVE_CONTEXT_SICK_GUARD_V1
                if (
                    intent == "CREATE_LEAVE"
                    and self._is_unsupported_sick_leave(
                        combined_text
                    )
                ):
                    await self._delete_conversation_state(
                        context
                    )

                    return {
                        "reply": (
                            "در حال حاضر دسترسی ثبت "
                            "مرخصی استعلاجی در این بخش "
                            "فعال نیست."
                        ),
                        "requiresConfirmation": False,
                    }

                response = (
                    await self._prepare_create_leave(
                        context,
                        combined_text,
                        dates,
                        times,
                    )
                )

                return await self._finalize_response_state(
                    context,
                    nlu_result,
                    conversation_payload,
                    response,
                    combined_text,
                )

            if intent in {
                "SHOW_ATTENDANCE",
                "CREATE_TIME_EVENT",
                "CREATE_TIME_EVENT_RANGE",
            }:
                response = (
                    await self._handle_attendance(
                        context,
                        combined_text,
                        dates,
                        times,
                        force_create=(
                            intent
                            in {
                                "CREATE_TIME_EVENT",
                                "CREATE_TIME_EVENT_RANGE",
                            }
                        ),
                        event_type=(
                            entities.get(
                                "eventType"
                            )
                        ),
                    )
                )

                return await self._finalize_response_state(
                    context,
                    nlu_result,
                    conversation_payload,
                    response,
                    combined_text,
                )

            try:
                legacy_dates = (
                    extract_jalali_dates(text)
                )
                legacy_times = extract_times(
                    text
                )
            except ValueError as exc:
                raise AppError(
                    str(exc),
                    code=(
                        "INVALID_DATE_OR_TIME"
                    ),
                ) from exc

            if self._is_food(text):
                response = await self._handle_food(
                    context,
                    text,
                    legacy_dates,
                    restaurant_validated=(
                        context.restaurant_id
                        is not None
                    ),
                    selected_restaurant=(
                        selected_restaurant
                    ),
                    conversation_payload=(
                        conversation_payload
                    ),
                )

                return await self._finalize_response_state(
                    context,
                    nlu_result,
                    conversation_payload,
                    response,
                    combined_text,
                )

            if self._is_leave_balance(text):
                data = await self.hr.get_time_account(
                    context,
                    (
                        legacy_dates[0]
                        if legacy_dates
                        else str(context.date)
                    ),
                )
                rows = data.get("data", data)

                return {
                    "reply": (
                        format_leave_balance_reply(
                            rows
                        )
                    ),
                    "requiresConfirmation": False,
                    "data": rows,
                }

            if self._is_leave_list(text):
                target_date = (
                    legacy_dates[0]
                    if legacy_dates
                    else str(context.date)
                )
                data = (
                    await self.hr.get_leave_requests(
                        context,
                        target_date,
                    )
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
                            if isinstance(
                                rows,
                                list,
                            )
                            else []
                        ),
                    },
                }

            if self._is_delete_leave(text):
                response = (
                    await self._prepare_delete_leave(
                        context,
                        text,
                        legacy_dates,
                    )
                )

                return await self._finalize_response_state(
                    context,
                    nlu_result,
                    conversation_payload,
                    response,
                    combined_text,
                )

            if self._is_leave_create(text):
                response = (
                    await self._prepare_create_leave(
                        context,
                        text,
                        legacy_dates,
                        legacy_times,
                    )
                )

                return await self._finalize_response_state(
                    context,
                    nlu_result,
                    conversation_payload,
                    response,
                    combined_text,
                )

            if self._is_attendance(text):
                response = (
                    await self._handle_attendance(
                        context,
                        text,
                        legacy_dates,
                        legacy_times,
                    )
                )

                return await self._finalize_response_state(
                    context,
                    nlu_result,
                    conversation_payload,
                    response,
                    combined_text,
                )

        except ValueError as exc:
            raise AppError(
                str(exc),
                code="INVALID_DATE_OR_TIME",
            ) from exc

        return {
            "reply": (
                nlu_result.get("clarification")
                or (
                    "درخواست را دقیق‌تر بگو. می‌توانم منوی غذا، "
                    "رزرو و لغو غذا، مانده و درخواست‌های مرخصی، "
                    "مأموریت، تردد و گزارش امروز را مدیریت کنم."
                )
            ),
            "requiresConfirmation": False,
            "suggestions": self._suggestions(),
        }

    @staticmethod
    def _is_contextual_guard_continuation(
        text: str,
        conversation_payload: dict[str, Any],
    ) -> bool:
        if not isinstance(
            conversation_payload,
            dict,
        ):
            return False

        if str(
            conversation_payload.get(
                "pendingActionId"
            )
            or ""
        ).strip():
            return True

        state = (
            conversation_payload.get(
                "nluState"
            )
            if isinstance(
                conversation_payload.get(
                    "nluState"
                ),
                dict,
            )
            else {}
        )

        domain = str(
            state.get("domain")
            or conversation_payload.get(
                "lastDomain"
            )
            or ""
        ).strip()

        if domain in {
            "",
            "UNKNOWN",
            "OUT_OF_SCOPE",
        }:
            return False

        missing_fields = (
            state.get(
                "missingFields"
            )
            if isinstance(
                state.get(
                    "missingFields"
                ),
                list,
            )
            else []
        )

        if not missing_fields:
            return False

        normalized = (
            normalize_nlu_text(
                text
            )
        )

        if not normalized:
            return False

        if re.search(
            r"[A-Za-z]",
            normalized,
        ):
            return False

        tokens = re.findall(
            (
                r"[0-9]+|"
                r"[\u0600-\u06FF]+"
            ),
            normalized,
        )

        if len(tokens) > 8:
            return False

        continuation_terms = {
            "صبح",
            "بامداد",
            "ظهر",
            "بعدازظهر",
            "عصر",
            "شب",
            "نیم",
            "ربع",
            "دقیقه",
            "ساعت",
            "امروز",
            "فردا",
            "پس",
            "روز",
            "ماه",
            "فروردین",
            "اردیبهشت",
            "خرداد",
            "تیر",
            "مرداد",
            "شهریور",
            "مهر",
            "آبان",
            "آذر",
            "دی",
            "بهمن",
            "اسفند",
            "ورود",
            "خروج",
            "استحقاقی",
            "استعلاجی",
            "ساعتی",
            "بله",
            "آره",
            "نه",
            "لغو",
            "تایید",
            "تأیید",
        }

        if any(
            token.isdigit()
            or token
            in continuation_terms
            for token in tokens
        ):
            return True

        # A short Persian reply is accepted only
        # while the agent is waiting for a field.
        return (
            bool(tokens)
            and len(tokens) <= 3
        )

    def _confirmation_replay_response(
        self,
        conversation_payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        cached = conversation_payload.get(
            "lastSuccessfulAction"
        )

        if not isinstance(cached, dict):
            return None

        try:
            completed_at = float(
                cached.get("completedAtEpoch")
            )
        except (TypeError, ValueError):
            return None

        age_seconds = time.time() - completed_at

        if (
            age_seconds < 0
            or age_seconds
            > CONFIRM_REPLAY_TTL_SECONDS
        ):
            return None

        action_id = str(
            cached.get("actionId") or ""
        ).strip()

        action_type = str(
            cached.get("actionType") or ""
        ).strip()

        if not action_id or not action_type:
            return None

        status = str(
            cached.get("status") or "succeeded"
        ).strip()

        reply = str(
            cached.get("reply")
            or self._action_success_reply(
                action_type
            )
        )

        return {
            "reply": reply,
            "requiresConfirmation": False,
            "action": {
                "id": action_id,
                "type": action_type,
                "status": status,
            },
            "data": cached.get("data"),
        }

    async def _wait_for_confirmation_replay(
        self,
        context: AgentContext,
    ) -> dict[str, Any] | None:
        interval_seconds = 0.2
        attempts = max(
            1,
            int(
                CONFIRM_REPLAY_WAIT_SECONDS
                / interval_seconds
            ),
        )

        for attempt in range(attempts):
            current_payload = (
                await self._load_conversation_payload(
                    context
                )
            )

            replay_response = (
                self._confirmation_replay_response(
                    current_payload
                )
            )

            if replay_response is not None:
                return replay_response

            if attempt + 1 < attempts:
                await asyncio.sleep(
                    interval_seconds
                )

        return None

    async def _handle_pending_action_reply(
        self,
        context: AgentContext,
        text: str,
        conversation_payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        reply_kind = (
            self._pending_action_reply_kind(
                text
            )
        )

        if reply_kind is None:
            return None

        employee_id = str(
            context.employee_id or ""
        ).strip()

        if not employee_id:
            raise AppError(
                "کد پرسنلی کاربر مشخص نیست.",
                code="MISSING_EMPLOYEE_ID",
            )

        pending_action = None
        pending_action_id = str(
            conversation_payload.get(
                "pendingActionId"
            )
            or ""
        ).strip()

        if pending_action_id:
            pending_action = (
                await asyncio.to_thread(
                    self.repository.get_pending_action,
                    pending_action_id,
                    employee_id,
                )
            )

            if (
                pending_action is not None
                and pending_action.status
                != "pending"
            ):
                pending_action = None

        if (
            pending_action is None
            and not str(
                context.conversation_id or ""
            ).strip()
        ):
            pending_action = (
                await asyncio.to_thread(
                    self.repository
                    .get_latest_pending_action,
                    employee_id,
                )
            )

        if reply_kind == "confirm":
            if pending_action is None:
                replay_response = (
                    self._confirmation_replay_response(
                        conversation_payload
                    )
                )

                if (
                    replay_response is None
                    and pending_action_id
                ):
                    replay_response = (
                        await self
                        ._wait_for_confirmation_replay(
                            context
                        )
                    )

                if replay_response is not None:
                    return replay_response

                return {
                    "reply": (
                        "در این مکالمه عملیاتی "
                        "در انتظار تأیید نیست."
                    ),
                    "requiresConfirmation": False,
                    "data": {
                        "pendingAction": None,
                    },
                }

            try:
                result = await self.actions.confirm(
                    context,
                    pending_action.id,
                )
            except AppError as exc:
                details = (
                    getattr(exc, "details", None)
                    or {}
                )

                current_status = str(
                    details.get("status") or ""
                ).strip()

                if (
                    getattr(
                        exc,
                        "status_code",
                        None,
                    )
                    == 409
                    and current_status
                    in {
                        "processing",
                        "succeeded",
                    }
                ):
                    replay_response = (
                        await self
                        ._wait_for_confirmation_replay(
                            context
                        )
                    )

                    if replay_response is not None:
                        return replay_response

                raise

            success_reply = (
                self._action_success_reply(
                    pending_action.action_type
                )
            )

            success_status = str(
                result.get("status")
                or "succeeded"
            )

            success_data = result.get(
                "result",
                result,
            )

            success_payload = dict(
                conversation_payload
            )

            success_payload.pop(
                "pendingActionId",
                None,
            )

            success_payload.pop(
                "proposal",
                None,
            )

            success_payload.pop(
                "proposalRejected",
                None,
            )

            if pending_action.action_type in {
                "RESERVE_FOOD",
                "CANCEL_FOOD",
                "CHANGE_FOOD",
            }:
                success_payload[
                    "lastDomain"
                ] = "FOOD"

                # Menu selection data is now stale.
                # The next request must read fresh API data.
                success_payload.pop(
                    "recentMenus",
                    None,
                )

            success_payload[
                "lastSuccessfulAction"
            ] = {
                "actionId": (
                    pending_action.id
                ),
                "actionType": (
                    pending_action.action_type
                ),
                "status": success_status,
                "reply": success_reply,
                "data": success_data,
                "completedAtEpoch": (
                    time.time()
                ),
            }

            await self._save_conversation_payload(
                context,
                success_payload,
            )

            return {
                "reply": success_reply,
                "requiresConfirmation": False,
                "action": {
                    "id": pending_action.id,
                    "type": (
                        pending_action.action_type
                    ),
                    "status": success_status,
                },
                "data": success_data,
            }

        if reply_kind == "reject":
            if pending_action is not None:
                await self.actions.cancel(
                    context,
                    pending_action.id,
                )

            if not conversation_payload:
                return {
                    "reply": (
                        "پیشنهاد فعالی برای رد کردن "
                        "در این مکالمه وجود ندارد."
                    ),
                    "requiresConfirmation": False,
                }

            updated_payload = dict(
                conversation_payload
            )
            updated_payload.pop(
                "pendingActionId",
                None,
            )
            proposal = (
                updated_payload.get("proposal")
                if isinstance(
                    updated_payload.get(
                        "proposal"
                    ),
                    dict,
                )
                else {}
            )
            updated_payload[
                "proposalRejected"
            ] = True

            nlu_state = (
                dict(
                    updated_payload.get(
                        "nluState"
                    )
                    or {}
                )
            )
            nlu_state[
                "proposalRejected"
            ] = True
            nlu_state[
                "missingFields"
            ] = ["alternative"]
            updated_payload[
                "nluState"
            ] = nlu_state

            await self._save_conversation_payload(
                context,
                updated_payload,
            )

            return {
                "reply": self._rejected_proposal_reply(
                    proposal,
                    updated_payload,
                ),
                "requiresConfirmation": False,
                "data": {
                    "proposalRejected": True,
                },
            }

        if pending_action is not None:
            result = await self.actions.cancel(
                context,
                pending_action.id,
            )
            message = (
                result.get("message")
                or "عملیات لغو شد."
            )
        else:
            message = (
                "فرایند فعال این مکالمه لغو شد."
            )

        await self._delete_conversation_state(
            context
        )

        return {
            "reply": message,
            "requiresConfirmation": False,
            "data": {
                "conversationCancelled": True,
            },
        }

    async def _load_conversation_payload(
        self,
        context: AgentContext,
    ) -> dict[str, Any]:
        employee_id = str(
            context.employee_id or ""
        ).strip()

        if not employee_id:
            return {}

        state = await asyncio.to_thread(
            self.repository.get_chat_state,
            employee_id,
            context.conversation_id,
        )

        if not state:
            return {}

        if str(
            state.get("stateType") or ""
        ) != CONVERSATION_STATE:
            return {}

        payload = state.get("payload")

        return (
            dict(payload)
            if isinstance(payload, dict)
            else {}
        )

    async def _save_conversation_payload(
        self,
        context: AgentContext,
        payload: dict[str, Any],
    ) -> None:
        employee_id = str(
            context.employee_id or ""
        ).strip()

        if not employee_id:
            return

        await asyncio.to_thread(
            self.repository.save_chat_state,
            employee_id,
            CONVERSATION_STATE,
            payload,
            CONVERSATION_STATE_TTL_MINUTES,
            context.conversation_id,
        )

    async def _delete_conversation_state(
        self,
        context: AgentContext,
    ) -> None:
        employee_id = str(
            context.employee_id or ""
        ).strip()

        if not employee_id:
            return

        await asyncio.to_thread(
            self.repository.delete_chat_state,
            employee_id,
            context.conversation_id,
        )

    @staticmethod
    def _apply_saved_restaurant(
        context: AgentContext,
        conversation_payload: dict[str, Any],
    ) -> tuple[
        AgentContext,
        dict[str, Any] | None,
    ]:
        restaurant = (
            conversation_payload.get(
                "restaurant"
            )
            if isinstance(
                conversation_payload.get(
                    "restaurant"
                ),
                dict,
            )
            else None
        )

        restaurant_id = (
            parse_int(
                restaurant.get(
                    "restaurantId"
                )
            )
            if restaurant
            else None
        )

        if restaurant_id is None:
            return context, restaurant

        updated_context = context.model_copy(
            update={
                "restaurant_id": restaurant_id,
                "meal_id": (
                    context.meal_id
                    or FOOD_MEAL_ID
                ),
            }
        )

        return updated_context, restaurant

    @staticmethod
    def _nlu_state_with_active_date(
        previous_state: dict[str, Any] | None,
        conversation_payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not previous_state:
            return previous_state

        active_date = str(
            conversation_payload.get(
                "activeDate"
            )
            or ""
        ).strip()

        if not active_date:
            return previous_state

        updated_state = dict(
            previous_state
        )
        entities = (
            dict(
                updated_state.get(
                    "entities"
                )
                or {}
            )
        )

        if (
            updated_state.get("domain")
            == "FOOD"
            and not entities.get("date")
        ):
            entities["date"] = active_date
            updated_state["entities"] = (
                entities
            )

        return updated_state

    def _enrich_food_nlu_result(
        self,
        nlu_result: dict[str, Any],
        text: str,
        conversation_payload: dict[str, Any],
    ) -> dict[str, Any]:
        result = dict(nlu_result)

        # FOOD_CONVERSATION_V1
        food_follow_up_candidates = (
            self._find_food_candidates(
                text,
                conversation_payload,
            )
        )

        candidate_dates = {
            str(
                item.get(
                    "day",
                    {},
                ).get("date")
                or ""
            ).strip()
            for item in food_follow_up_candidates
            if isinstance(
                item,
                dict,
            )
            and str(
                item.get(
                    "day",
                    {},
                ).get("date")
                or ""
            ).strip()
        }

        unique_candidate_date = (
            next(
                iter(candidate_dates)
            )
            if len(candidate_dates) == 1
            else None
        )

        is_food_follow_up = (
            str(
                conversation_payload.get(
                    "lastDomain"
                )
                or ""
            )
            == "FOOD"
            and bool(
                conversation_payload.get(
                    "recentMenus"
                )
            )
            and (
                bool(
                    self._infer_menu_date(
                        text,
                        conversation_payload,
                    )
                )
                or bool(
                    food_follow_up_candidates
                )
            )
        )

        if (
            result.get("domain")
            in {"UNKNOWN", "OUT_OF_SCOPE"}
            and is_food_follow_up
        ):
            inferred_date = (
                self._infer_menu_date(
                    text,
                    conversation_payload,
                )
                or unique_candidate_date
                or conversation_payload.get(
                    "activeDate"
                )
            )
            entities: dict[str, Any] = {}

            if inferred_date:
                entities["date"] = str(
                    inferred_date
                )

            missing_fields = (
                []
                if inferred_date
                else ["date"]
            )

            result = {
                "domain": "FOOD",
                "intent": "RESERVE_FOOD",
                "entities": entities,
                "confidence": 0.95,
                "missingFields": missing_fields,
                "needsClarification": bool(
                    missing_fields
                ),
                "conversationComplete": False,
                "clarification": (
                    "برای چه روزی غذا رزرو شود؟"
                    if missing_fields
                    else None
                ),
                "errors": [],
                "state": {
                    "domain": "FOOD",
                    "intent": "RESERVE_FOOD",
                    "entities": entities,
                    "missingFields": (
                        missing_fields
                    ),
                },
            }

        if (
            result.get("domain")
            != "FOOD"
            or result.get("intent")
            != "RESERVE_FOOD"
        ):
            return result

        entities = dict(
            result.get("entities")
            or {}
        )

        inferred_date = (
            entities.get("date")
            or self._infer_menu_date(
                text,
                conversation_payload,
            )
            or unique_candidate_date
            or conversation_payload.get(
                "activeDate"
            )
        )

        if inferred_date:
            entities["date"] = str(
                inferred_date
            )
            result["entities"] = entities

            missing_fields = [
                item
                for item in (
                    result.get(
                        "missingFields"
                    )
                    or []
                )
                if item != "date"
            ]
            result["missingFields"] = (
                missing_fields
            )
            result["needsClarification"] = (
                bool(
                    missing_fields
                    or result.get("errors")
                )
            )

            state = dict(
                result.get("state")
                or {}
            )
            state["domain"] = "FOOD"
            state["intent"] = (
                "RESERVE_FOOD"
            )
            state["entities"] = entities
            state["missingFields"] = (
                missing_fields
            )
            state.pop(
                "proposalRejected",
                None,
            )
            result["state"] = state

            if not result[
                "needsClarification"
            ]:
                result["clarification"] = (
                    None
                )

        return result

    def _combined_conversation_text(
        self,
        text: str,
        conversation_payload: dict[str, Any],
        nlu_result: dict[str, Any],
    ) -> str:
        previous_domain = str(
            conversation_payload.get(
                "lastDomain"
            )
            or ""
        )
        current_domain = str(
            nlu_result.get("domain")
            or ""
        )

        previous_text = str(
            conversation_payload.get(
                "originalMessage"
            )
            or ""
        ).strip()

        if (
            previous_domain == "FOOD"
            and current_domain == "FOOD"
            and conversation_payload.get(
                "proposalRejected"
            )
        ):
            proposal = (
                conversation_payload.get(
                    "proposal"
                )
                if isinstance(
                    conversation_payload.get(
                        "proposal"
                    ),
                    dict,
                )
                else {}
            )
            proposal_data = (
                proposal.get("data")
                if isinstance(
                    proposal.get("data"),
                    dict,
                )
                else {}
            )
            proposal_food = (
                proposal_data.get("food")
                if isinstance(
                    proposal_data.get("food"),
                    dict,
                )
                else {}
            )
            previous_food_name = str(
                proposal_food.get(
                    "foodName"
                )
                or ""
            ).strip()

            current_food_candidates = (
                self._find_food_candidates(
                    text,
                    conversation_payload,
                )
            )

            if current_food_candidates:
                return (
                    f"{text} رزرو کن"
                ).strip()

            if (
                previous_food_name
                and self._infer_menu_date(
                    text,
                    conversation_payload,
                )
            ):
                return (
                    f"{previous_food_name} "
                    f"{text} رزرو کن"
                ).strip()

        previous_nlu_state = (
            conversation_payload.get(
                "nluState"
            )
            if isinstance(
                conversation_payload.get(
                    "nluState"
                ),
                dict,
            )
            else {}
        )
        previous_intent = str(
            previous_nlu_state.get(
                "intent"
            )
            or ""
        )
        current_intent = str(
            nlu_result.get("intent")
            or ""
        )

        is_explicit_new_request = (
            self._looks_like_new_request(
                text
            )
            or (
                current_domain == "FOOD"
                and bool(
                    self._find_food_candidates(
                        text,
                        conversation_payload,
                    )
                )
                and any(
                    keyword in text
                    for keyword in {
                        "رزرو",
                        "بگیر",
                        "سفارش",
                    }
                )
            )
        )

        if (
            previous_text
            and previous_domain
            and previous_domain
            == current_domain
            and previous_intent
            == current_intent
            and not is_explicit_new_request
        ):
            return (
                f"{previous_text} {text}"
            ).strip()

        return text

    async def _cancel_pending_on_domain_switch(
        self,
        context: AgentContext,
        conversation_payload: dict[str, Any],
        nlu_result: dict[str, Any],
    ) -> None:
        pending_action_id = str(
            conversation_payload.get(
                "pendingActionId"
            )
            or ""
        ).strip()

        if not pending_action_id:
            return

        current_domain = str(
            nlu_result.get("domain")
            or ""
        )

        if current_domain in {
            "",
            "UNKNOWN",
            "OUT_OF_SCOPE",
        }:
            return

        try:
            await self.actions.cancel(
                context,
                pending_action_id,
            )
        except AppError:
            pass

        conversation_payload.pop(
            "pendingActionId",
            None,
        )
        conversation_payload.pop(
            "proposal",
            None,
        )
        conversation_payload.pop(
            "proposalRejected",
            None,
        )

    @staticmethod
    def _dates_from_entities(
        entities: dict[str, Any],
    ) -> list[str]:
        values: list[str] = []

        for key in (
            "startDate",
            "endDate",
            "date",
        ):
            value = str(
                entities.get(key) or ""
            ).strip()

            if value and value not in values:
                values.append(value)

        return values

    @staticmethod
    def _times_from_entities(
        entities: dict[str, Any],
    ) -> list[str]:
        values: list[str] = []

        for key in (
            "startTime",
            "endTime",
            "time",
        ):
            value = str(
                entities.get(key) or ""
            ).strip()

            if value and value not in values:
                values.append(value)

        return values

    async def _finalize_response_state(
        self,
        context: AgentContext,
        nlu_result: dict[str, Any],
        conversation_payload: dict[str, Any],
        response: dict[str, Any],
        combined_text: str,
    ) -> dict[str, Any]:
        response_data = (
            response.get("data")
            if isinstance(
                response.get("data"),
                dict,
            )
            else {}
        )

        if (
            response_data.get(
                "awaitingRestaurantConfirmation"
            )
            or response_data.get(
                "awaitingRestaurantSelection"
            )
        ):
            return response

        updated_payload = dict(
            conversation_payload
        )
        updated_payload.update(
            {
                "nluState": (
                    nlu_result.get("state")
                    or {
                        "domain": (
                            nlu_result.get(
                                "domain"
                            )
                        ),
                        "intent": (
                            nlu_result.get(
                                "intent"
                            )
                        ),
                        "entities": (
                            nlu_result.get(
                                "entities"
                            )
                            or {}
                        ),
                        "missingFields": [],
                    }
                ),
                "originalMessage": (
                    combined_text
                ),
                "lastDomain": (
                    nlu_result.get("domain")
                ),
            }
        )

        # LEAVE_CONTEXT_SICK_GUARD_V1
        response_missing_field = str(
            response_data.get(
                "missingField"
            )
            or ""
        ).strip()

        if response_missing_field:
            saved_nlu_state = dict(
                updated_payload.get(
                    "nluState"
                )
                or {}
            )

            saved_missing_fields = [
                str(item)
                for item in (
                    saved_nlu_state.get(
                        "missingFields"
                    )
                    or []
                )
                if str(item).strip()
            ]

            if (
                response_missing_field
                not in saved_missing_fields
            ):
                saved_missing_fields.append(
                    response_missing_field
                )

            saved_nlu_state[
                "missingFields"
            ] = saved_missing_fields

            updated_payload[
                "nluState"
            ] = saved_nlu_state

        data = response_data

        response_date = str(
            data.get("date")
            or ""
        ).strip()

        if (
            response_date
            and str(
                nlu_result.get(
                    "domain"
                )
                or ""
            )
            == "FOOD"
        ):
            saved_nlu_state = dict(
                updated_payload.get(
                    "nluState"
                )
                or {}
            )

            saved_entities = dict(
                saved_nlu_state.get(
                    "entities"
                )
                or {}
            )

            saved_entities[
                "date"
            ] = response_date

            saved_nlu_state[
                "domain"
            ] = "FOOD"

            saved_nlu_state[
                "entities"
            ] = saved_entities

            updated_payload[
                "nluState"
            ] = saved_nlu_state

            updated_payload[
                "activeDate"
            ] = response_date

        restaurant = data.get(
            "restaurant"
        )

        if isinstance(restaurant, dict):
            updated_payload[
                "restaurant"
            ] = restaurant

        days = data.get("days")

        if not isinstance(days, list):
            menu_data = (
                data.get("menu")
                if isinstance(
                    data.get("menu"),
                    dict,
                )
                else {}
            )
            days = menu_data.get("days")

        if isinstance(days, list):
            updated_payload[
                "recentMenus"
            ] = self._merge_menu_days(
                updated_payload.get(
                    "recentMenus"
                ),
                days,
            )

            if len(days) == 1:
                updated_payload[
                    "activeDate"
                ] = days[0].get(
                    "date"
                )

        pending_action = (
            response.get("pendingAction")
            if isinstance(
                response.get(
                    "pendingAction"
                ),
                dict,
            )
            else {}
        )

        pending_action_id = str(
            pending_action.get("id")
            or ""
        ).strip()

        if pending_action_id:
            updated_payload[
                "pendingActionId"
            ] = pending_action_id
            updated_payload[
                "proposal"
            ] = {
                "actionType": (
                    nlu_result.get("intent")
                ),
                "data": data,
                "reply": response.get(
                    "reply"
                ),
            }
            updated_payload.pop(
                "proposalRejected",
                None,
            )
        else:
            updated_payload.pop(
                "pendingActionId",
                None,
            )

        should_preserve = bool(
            pending_action_id
            or updated_payload.get(
                "recentMenus"
            )
            or nlu_result.get(
                "needsClarification"
            )
            or not nlu_result.get(
                "conversationComplete",
                False,
            )
        )

        if should_preserve:
            await self._save_conversation_payload(
                context,
                updated_payload,
            )
        else:
            await self._delete_conversation_state(
                context
            )

        return response

    @staticmethod
    def _merge_menu_days(
        existing: Any,
        new_days: list[Any],
    ) -> list[dict[str, Any]]:
        merged: dict[
            str,
            dict[str, Any],
        ] = {}

        if isinstance(existing, list):
            for day in existing:
                if not isinstance(day, dict):
                    continue

                key = str(
                    day.get("date")
                    or day.get("dayOfWeek")
                    or len(merged)
                )
                merged[key] = dict(day)

        for day in new_days:
            if not isinstance(day, dict):
                continue

            key = str(
                day.get("date")
                or day.get("dayOfWeek")
                or len(merged)
            )
            merged[key] = dict(day)

        return list(merged.values())[-14:]

    @staticmethod
    def _infer_menu_date(
        text: str,
        conversation_payload: dict[str, Any],
    ) -> str | None:
        normalized = normalize_nlu_text(
            text
        )

        recent_menus = (
            conversation_payload.get(
                "recentMenus"
            )
            or []
        )

        for day in recent_menus:
            if not isinstance(day, dict):
                continue

            date_value = str(
                day.get("date") or ""
            ).strip()
            day_name = normalize_nlu_text(
                day.get("dayOfWeek")
                or ""
            )

            if (
                date_value
                and date_value in normalized
            ):
                return date_value

            if (
                day_name
                and day_name in normalized
            ):
                return date_value or None

        return None

    @staticmethod
    def _rejected_proposal_reply(
        proposal: dict[str, Any],
        conversation_payload: dict[str, Any],
    ) -> str:
        action_type = str(
            proposal.get("actionType")
            or ""
        )
        data = (
            proposal.get("data")
            if isinstance(
                proposal.get("data"),
                dict,
            )
            else {}
        )

        if action_type == "RESERVE_FOOD":
            food = (
                data.get("food")
                if isinstance(
                    data.get("food"),
                    dict,
                )
                else {}
            )
            food_name = str(
                food.get("foodName")
                or "این غذا"
            )
            target_date = str(
                data.get("date")
                or conversation_payload.get(
                    "activeDate"
                )
                or "این روز"
            )
            target_label = str(
                data.get("dayOfWeek")
                or target_date
            )

            alternatives = (
                conversation_payload.get(
                    "recentMenus"
                )
                or []
            )
            other_dates: list[str] = []

            for day in alternatives:
                if not isinstance(day, dict):
                    continue

                day_date = str(
                    day.get("date") or ""
                )

                if (
                    not day_date
                    or day_date == target_date
                ):
                    continue

                foods = day.get("foods") or []

                if any(
                    normalize_nlu_text(
                        item.get("foodName")
                        or ""
                    )
                    == normalize_nlu_text(
                        food_name
                    )
                    for item in foods
                    if isinstance(item, dict)
                ):
                    other_dates.append(
                        str(
                            day.get("dayOfWeek")
                            or day_date
                        )
                    )

            other_date_text = (
                other_dates[0]
                if other_dates
                else "روز دیگری"
            )

            return (
                f"باشه، «{food_name}» "
                f"{target_label} را رزرو نمی‌کنم. "
                f"منظورتان {other_date_text} بود "
                f"یا غذای دیگری برای {target_label}؟"
            )

        return (
            "باشه، پیشنهاد فعلی اجرا نمی‌شود. "
            "جزئیات جایگزین را بفرمایید."
        )

    @staticmethod
    def _pending_action_reply_kind(
        text: str,
    ) -> str | None:
        normalized = normalize_persian_text(
            text
        )

        normalized = re.sub(
            r"[،,؛;.!؟?]+",
            " ",
            normalized,
        )

        normalized = re.sub(
            r"\s+",
            " ",
            normalized,
        ).strip()

        confirm_phrases = {
            "بله",
            "اره",
            "آره",
            "اوکی",
            "باشه",
            "تایید",
            "تأیید",
            "تایید میکنم",
            "تأیید میکنم",
            "تایید می کنم",
            "تأیید می کنم",
            "انجام بده",
            "ادامه بده",
            "بله انجام بده",
            "بله تایید میکنم",
            "بله تأیید میکنم",
            "بله لطفا",
            "بله لطفاً",
            "yes",
            "ok",
            "confirm",
        }

        reject_phrases = {
            "نه",
            "خیر",
            "نه ممنون",
            "خیر ممنون",
            "no",
        }

        cancel_phrases = {
            "لغو",
            "لغو کن",
            "حذف",
            "حذف کن",
            "کنسل",
            "کنسل کن",
            "بیخیال",
            "بی خیال",
            "انصراف",
            "نمیخوام",
            "نمی خواهم",
            "نمیخوامش",
            "cancel",
        }

        if normalized in confirm_phrases:
            return "confirm"

        if normalized in reject_phrases:
            return "reject"

        if normalized in cancel_phrases:
            return "cancel"

        return None

    @staticmethod
    def _action_success_reply(
        action_type: str,
    ) -> str:
        messages = {
            "RESERVE_FOOD": (
                "رزرو غذا با موفقیت انجام شد."
            ),
            "CANCEL_FOOD": (
                "رزرو غذا با موفقیت لغو شد."
            ),
            "CHANGE_FOOD": (
                "رزرو غذا با موفقیت تغییر کرد."
            ),
            "RATE_FOOD": (
                "امتیاز غذا با موفقیت ثبت شد."
            ),
            "CREATE_LEAVE": (
                "✅ درخواست مرخصی با موفقیت ثبت شد."
            ),
            "DELETE_LEAVE": (
                "درخواست با موفقیت حذف شد."
            ),
            "CREATE_TIME_EVENT": (
                "تردد با موفقیت ثبت شد."
            ),
        }

        return messages.get(
            action_type,
            "عملیات با موفقیت انجام شد.",
        )

    async def _handle_pending_chat_state(
        self,
        context: AgentContext,
        text: str,
    ) -> dict[str, Any] | None:
        employee_id = str(
            context.employee_id or ""
        ).strip()

        if not employee_id:
            return None

        conversation_id = (
            context.conversation_id
        )

        state = await asyncio.to_thread(
            self.repository.get_chat_state,
            employee_id,
            conversation_id,
        )

        if not state:
            return None

        state_type = str(
            state.get("stateType") or ""
        ).strip()
        payload = state.get("payload") or {}

        if not isinstance(payload, dict):
            await asyncio.to_thread(
                self.repository.delete_chat_state,
                employee_id,
                conversation_id,
            )
            return None

        if state_type == CONVERSATION_STATE:
            return None

        if state_type not in {
            FOOD_RESTAURANT_CONFIRM_STATE,
            FOOD_RESTAURANT_SELECT_STATE,
        }:
            await asyncio.to_thread(
                self.repository.delete_chat_state,
                employee_id,
                conversation_id,
            )
            return None

        restaurants = payload.get(
            "restaurants"
        ) or []
        restaurants = [
            item
            for item in restaurants
            if isinstance(item, dict)
            and parse_int(
                item.get("restaurantId")
            )
        ]

        if not restaurants:
            await asyncio.to_thread(
                self.repository.delete_chat_state,
                employee_id,
                conversation_id,
            )
            return None

        reply_kind = (
            self._pending_action_reply_kind(
                text
            )
        )

        if reply_kind in {
            "reject",
            "cancel",
        }:
            await asyncio.to_thread(
                self.repository.delete_chat_state,
                employee_id,
                conversation_id,
            )

            previous_payload = payload.get(
                "conversationPayload"
            )

            if isinstance(
                previous_payload,
                dict,
            ) and previous_payload:
                await self._save_conversation_payload(
                    context,
                    previous_payload,
                )

            return {
                "reply": (
                    "باشه، این رستوران انتخاب نشد. "
                    "می‌توانید درخواست دیگری بفرستید."
                    if reply_kind == "reject"
                    else (
                        "فرایند انتخاب رستوران "
                        "لغو شد."
                    )
                ),
                "requiresConfirmation": False,
            }

        selected_restaurant = (
            self._match_restaurant_reply(
                text,
                restaurants,
            )
        )

        if (
            state_type
            == FOOD_RESTAURANT_CONFIRM_STATE
            and selected_restaurant is None
            and self._is_positive_reply(text)
        ):
            selected_restaurant = (
                restaurants[0]
            )

        if selected_restaurant is not None:
            await asyncio.to_thread(
                self.repository.delete_chat_state,
                employee_id,
                conversation_id,
            )

            return await self._resume_food_request(
                context,
                payload,
                selected_restaurant,
            )

        if self._looks_like_new_request(
            text
        ):
            await asyncio.to_thread(
                self.repository.delete_chat_state,
                employee_id,
                conversation_id,
            )
            return None

        if (
            state_type
            == FOOD_RESTAURANT_CONFIRM_STATE
        ):
            restaurant = restaurants[0]

            return {
                "reply": (
                    f"رستوران مجاز شما "
                    f"«{restaurant.get('restaurantName')}» است. "
                    "برای ادامه فقط «بله» یا «خیر» بفرستید."
                ),
                "requiresConfirmation": False,
                "data": {
                    "awaitingRestaurantConfirmation": True,
                    "restaurant": restaurant,
                },
            }

        return {
            "reply": self._restaurant_selection_prompt(
                restaurants
            ),
            "requiresConfirmation": False,
            "data": {
                "awaitingRestaurantSelection": True,
                "restaurants": restaurants,
            },
        }

    async def _resume_food_request(
        self,
        context: AgentContext,
        payload: dict[str, Any],
        restaurant: dict[str, Any],
    ) -> dict[str, Any]:
        restaurant_id = parse_int(
            restaurant.get("restaurantId")
        )

        if restaurant_id is None:
            raise AppError(
                "شناسه رستوران انتخاب‌شده معتبر نیست.",
                code="INVALID_RESTAURANT",
            )

        original_message = str(
            payload.get("originalMessage")
            or "منوی غذا را نشان بده"
        )
        original_text = normalize_persian_text(
            original_message
        )

        target_date = payload.get(
            "targetDate"
        )
        context_date = payload.get(
            "contextDate"
        )

        context_updates: dict[str, Any] = {
            "restaurant_id": restaurant_id,
            "meal_id": FOOD_MEAL_ID,
        }

        if context_date:
            context_updates["date"] = (
                context_date
            )

        food_context = context.model_copy(
            update=context_updates
        )

        dates = (
            [str(target_date)]
            if target_date
            else []
        )

        conversation_payload = (
            payload.get(
                "conversationPayload"
            )
            if isinstance(
                payload.get(
                    "conversationPayload"
                ),
                dict,
            )
            else {}
        )

        nlu_result = analyze_message(
            original_message,
            reference_date=str(
                food_context.date or ""
            ),
            conversation_state=(
                conversation_payload.get(
                    "nluState"
                )
                if isinstance(
                    conversation_payload.get(
                        "nluState"
                    ),
                    dict,
                )
                else None
            ),
        )

        nlu_result = (
            self._enrich_food_nlu_result(
                nlu_result,
                original_text,
                conversation_payload,
            )
        )

        response = await self._handle_food(
            food_context,
            original_text,
            dates,
            restaurant_validated=True,
            selected_restaurant=restaurant,
            conversation_payload=(
                conversation_payload
            ),
        )

        return await self._finalize_response_state(
            food_context,
            nlu_result,
            conversation_payload,
            response,
            original_text,
        )

    async def _begin_restaurant_selection(
        self,
        context: AgentContext,
        text: str,
        target_date: str | None,
        conversation_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        employee_id = str(
            context.employee_id or ""
        ).strip()

        if not employee_id:
            raise AppError(
                "کد پرسنلی کاربر برای دریافت رستوران‌ها مشخص نیست.",
                code="MISSING_EMPLOYEE_ID",
            )

        conversation_id = (
            context.conversation_id
        )

        restaurants = (
            await self.food.get_my_restaurants(
                context
            )
        )

        if not restaurants:
            return {
                "reply": (
                    "برای شما رستوران مجازی تعریف نشده است. "
                    "لطفاً با واحد مربوطه تماس بگیرید."
                ),
                "requiresConfirmation": False,
                "data": {
                    "restaurants": [],
                },
            }

        state_payload = {
            "originalMessage": text,
            "targetDate": target_date,
            "contextDate": context.date,
            "restaurants": restaurants,
            "conversationPayload": (
                dict(
                    conversation_payload
                    or {}
                )
            ),
        }

        if len(restaurants) == 1:
            restaurant = restaurants[0]

            await asyncio.to_thread(
                self.repository.save_chat_state,
                employee_id,
                FOOD_RESTAURANT_CONFIRM_STATE,
                state_payload,
                FOOD_CHAT_STATE_TTL_MINUTES,
                conversation_id,
            )

            return {
                "reply": (
                    f"رستوران مجاز شما "
                    f"«{restaurant.get('restaurantName')}» است. "
                    "منوی همین رستوران را بررسی کنم؟"
                ),
                "requiresConfirmation": False,
                "data": {
                    "awaitingRestaurantConfirmation": True,
                    "restaurant": restaurant,
                    "expiresInMinutes": (
                        FOOD_CHAT_STATE_TTL_MINUTES
                    ),
                },
            }

        await asyncio.to_thread(
            self.repository.save_chat_state,
            employee_id,
            FOOD_RESTAURANT_SELECT_STATE,
            state_payload,
            FOOD_CHAT_STATE_TTL_MINUTES,
            conversation_id,
        )

        return {
            "reply": (
                self._restaurant_selection_prompt(
                    restaurants
                )
            ),
            "requiresConfirmation": False,
            "data": {
                "awaitingRestaurantSelection": True,
                "restaurants": restaurants,
                "expiresInMinutes": (
                    FOOD_CHAT_STATE_TTL_MINUTES
                ),
            },
        }

    @staticmethod
    def _restaurant_selection_prompt(
        restaurants: list[dict[str, Any]],
    ) -> str:
        lines = [
            "شما به چند رستوران دسترسی دارید. "
            "لطفاً شماره یا نام رستوران موردنظر را بفرستید:"
        ]

        for index, restaurant in enumerate(
            restaurants,
            start=1,
        ):
            restaurant_name = (
                restaurant.get("restaurantName")
                or "رستوران بدون نام"
            )
            lines.append(
                f"{index}. {restaurant_name}"
            )

        return "\n".join(lines)

    @staticmethod
    def _match_restaurant_reply(
        text: str,
        restaurants: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        normalized_text = normalize_persian_text(
            text
        ).strip()

        compact_text = re.sub(
            r"\s+",
            " ",
            normalized_text,
        )

        for restaurant in restaurants:
            restaurant_name = normalize_persian_text(
                str(
                    restaurant.get("restaurantName")
                    or ""
                )
            ).strip()

            if not restaurant_name:
                continue

            short_name = restaurant_name.replace(
                "رستوران",
                "",
            ).strip()

            if (
                restaurant_name == compact_text
                or restaurant_name in compact_text
                or (
                    len(short_name) >= 3
                    and short_name in compact_text
                )
            ):
                return restaurant

        numbers = [
            parse_int(value)
            for value in re.findall(
                r"\d+",
                compact_text,
            )
        ]
        numbers = [
            value
            for value in numbers
            if value is not None
        ]

        for number in numbers:
            for restaurant in restaurants:
                if (
                    parse_int(
                        restaurant.get("restaurantId")
                    )
                    == number
                ):
                    return restaurant

        for number in numbers:
            if 1 <= number <= len(restaurants):
                return restaurants[number - 1]

        return None

    @staticmethod
    def _is_positive_reply(text: str) -> bool:
        normalized = normalize_persian_text(
            text
        ).strip()

        positive_phrases = {
            "بله",
            "اره",
            "آره",
            "اوکی",
            "باشه",
            "تایید",
            "تأیید",
            "ادامه بده",
            "بررسی کن",
            "انجام بده",
        }

        return any(
            phrase == normalized
            or phrase in normalized
            for phrase in positive_phrases
        )

    @staticmethod
    def _is_negative_reply(text: str) -> bool:
        normalized = normalize_persian_text(
            text
        ).strip()

        negative_phrases = {
            "خیر",
            "نه",
            "لغو",
            "بیخیال",
            "بی خیال",
            "انصراف",
            "نمیخوام",
            "نمی خواهم",
            "نمیخوامش",
        }

        return any(
            phrase == normalized
            or phrase in normalized
            for phrase in negative_phrases
        )

    @staticmethod
    def _is_unsupported_sick_leave(
        text: str,
    ) -> bool:
        normalized = normalize_nlu_text(
            text or ""
        )

        return "استعلاجی" in normalized

    def _looks_like_new_request(
        self,
        text: str,
    ) -> bool:
        return (
            self._is_help(text)
            or self._is_daily_brief(text)
            or self._is_food(text)
            or self._is_leave_balance(text)
            or self._is_leave_list(text)
            or self._is_delete_leave(text)
            or self._is_leave_create(text)
            or self._is_attendance(text)
            or self._is_greeting(text)
        )

    @staticmethod
    def _is_help(text: str) -> bool:
        return any(
            keyword in text
            for keyword in [
                "راهنما",
                "کمک",
                "چه کار",
                "قابلیت",
                "چی بلدی",
            ]
        )

    @staticmethod
    def _is_greeting(text: str) -> bool:
        return text in {
            "سلام",
            "درود",
            "سلام خوبی",
            "صبح بخیر",
            "عصر بخیر",
            "شب بخیر",
        }

    @staticmethod
    def _is_daily_brief(text: str) -> bool:
        return any(
            keyword in text
            for keyword in [
                "گزارش امروز",
                "خلاصه امروز",
                "وضعیت امروز",
                "گزارش روزانه",
            ]
        )

    @staticmethod
    def _food_mutation_kind(
        text: str,
    ) -> str | None:
        normalized = normalize_nlu_text(
            text or ""
        )

        change_terms = (
            "تغییر بده",
            "تغییرش بده",
            "تغییر کن",
            "عوض کن",
            "عوضش کن",
            "جایگزین",
            "جایگزین کن",
            "جایگزینش کن",
            "به جای",
            "بجای",
            "بجاش",
            "بکن",
            "تبدیل کن",
            "بردار و",
        )

        cancel_terms = (
            "حذف کن",
            "حذفش کن",
            "حذف شه",
            "حذف شود",
            "لغو کن",
            "لغوش کن",
            "لغو شه",
            "لغو شود",
            "کنسل کن",
            "کنسلش کن",
            "بردار",
            "برش دار",
            "پاک کن",
            "نمیخوام",
            "نمی خواهم",
        )

        if any(
            term in normalized
            for term in change_terms
        ):
            return "change"

        if any(
            term in normalized
            for term in cancel_terms
        ):
            return "cancel"

        return None

    @staticmethod
    def _normalize_food_mutation_text(
        text: str,
    ) -> str:
        normalized = normalize_nlu_text(
            text or ""
        )

        typo_replacements = {
            "یکشنیه": "یکشنبه",
            "یکشنیه": "یکشنبه",
            "یکشبه": "یکشنبه",
            "دوشنبه": "دوشنبه",
            "سهشنه": "سه شنبه",
            "سهشنیه": "سه شنبه",
            "چهارشنه": "چهارشنبه",
            "پنجشنه": "پنجشنبه",
        }

        for wrong, correct in (
            typo_replacements.items()
        ):
            normalized = normalized.replace(
                wrong,
                correct,
            )

        return normalized

    @staticmethod
    def _food_name_match_score(
        text: str,
        food_name: str,
    ) -> int:
        normalized_text = (
            ChatService
            ._normalize_food_mutation_text(
                text
            )
        )

        normalized_name = normalize_nlu_text(
            food_name or ""
        ).strip()

        if not normalized_name:
            return 0

        score = 0

        if normalized_name in normalized_text:
            score += 100

        name_tokens = set(
            re.findall(
                r"[a-zA-Z]+|[0-9]+|"
                r"[\u0600-\u06FF]+",
                normalized_name,
            )
        )

        ignored_tokens = {
            "غذا",
            "غذای",
            "خورشت",
            "خوراک",
            "پلو",
            "با",
            "و",
        }

        useful_tokens = {
            token
            for token in name_tokens
            if token not in ignored_tokens
            and not token.isdigit()
            and len(token) >= 3
        }

        for token in useful_tokens:
            if token in normalized_text:
                score += 15

        if useful_tokens and all(
            token in normalized_text
            for token in useful_tokens
        ):
            score += 30

        return score

    @classmethod
    def _foods_mentioned_in_text(
        cls,
        text: str,
        days: list[dict[str, Any]],
    ) -> list[
        tuple[
            int,
            dict[str, Any],
            dict[str, Any],
        ]
    ]:
        matches: list[
            tuple[
                int,
                dict[str, Any],
                dict[str, Any],
            ]
        ] = []

        for day in days:
            if not isinstance(day, dict):
                continue

            for food in (
                day.get("foods")
                or []
            ):
                if not isinstance(food, dict):
                    continue

                score = (
                    cls._food_name_match_score(
                        text,
                        str(
                            food.get(
                                "foodName"
                            )
                            or ""
                        ),
                    )
                )

                if score <= 0:
                    continue

                matches.append(
                    (
                        score,
                        dict(day),
                        dict(food),
                    )
                )

        matches.sort(
            key=lambda item: (
                item[0],
                str(
                    item[1].get("date")
                    or ""
                ),
            ),
            reverse=True,
        )

        return matches

    @classmethod
    def _resolve_food_mutation_day(
        cls,
        text: str,
        days: list[dict[str, Any]],
        reference_date: str,
    ) -> dict[str, Any] | None:
        normalized = (
            cls._normalize_food_mutation_text(
                text
            )
        )

        compact_text = re.sub(
            r"\s+",
            "",
            normalized,
        )

        # Exact Jalali date from menu.
        for day in days:
            if not isinstance(day, dict):
                continue

            date_value = str(
                day.get("date")
                or ""
            ).strip()

            if not date_value:
                continue

            compact_date = re.sub(
                r"\s+",
                "",
                date_value,
            )

            if (
                date_value in normalized
                or compact_date in compact_text
            ):
                return dict(day)

        # Explicit weekday, including common typos.
        requested_weekday = (
            cls._requested_weekday(
                normalized
            )
        )

        if requested_weekday:
            resolved_date = (
                cls._infer_menu_date_from_days(
                    normalized,
                    days,
                )
            )

            if resolved_date:
                for day in days:
                    if (
                        isinstance(day, dict)
                        and str(
                            day.get("date")
                            or ""
                        )
                        == str(resolved_date)
                    ):
                        return dict(day)

        # Relative date such as today/tomorrow.
        try:
            date_nlu = analyze_message(
                normalized,
                reference_date=(
                    reference_date
                ),
                conversation_state=None,
            )

            entities = (
                date_nlu.get("entities")
                if isinstance(
                    date_nlu.get(
                        "entities"
                    ),
                    dict,
                )
                else {}
            )

            nlu_date = str(
                entities.get("date")
                or entities.get(
                    "startDate"
                )
                or ""
            ).strip()

            if nlu_date:
                for day in days:
                    if (
                        isinstance(day, dict)
                        and str(
                            day.get("date")
                            or ""
                        )
                        == nlu_date
                    ):
                        return dict(day)

        except Exception:
            pass

        # When only one active reservation exists,
        # allow phrases such as "رزرو غذام رو حذف کن".
        selected_days = [
            dict(day)
            for day in days
            if isinstance(day, dict)
            and parse_int(
                day.get(
                    "selectedPlanDetailId"
                )
            )
            not in {
                None,
                0,
            }
        ]

        if len(selected_days) == 1:
            return selected_days[0]

        return None

    async def _handle_explicit_food_mutation(
        self,
        context: AgentContext,
        text: str,
        conversation_payload: dict[str, Any],
        selected_restaurant: (
            dict[str, Any]
            | None
        ),
    ) -> dict[str, Any] | None:
        mutation_kind = (
            self._food_mutation_kind(
                text
            )
        )

        if mutation_kind is None:
            return None

        normalized = (
            self._normalize_food_mutation_text(
                text
            )
        )

        other_domain_terms = (
            "مرخصی",
            "ماموریت",
            "مأموریت",
            "تردد",
            "ورود",
            "خروج",
            "اضافه کاری",
            "اضافه‌کاری",
        )

        if any(
            term in normalized
            for term in other_domain_terms
        ):
            return None

        restaurant = (
            selected_restaurant
            if isinstance(
                selected_restaurant,
                dict,
            )
            else (
                conversation_payload.get(
                    "restaurant"
                )
                if isinstance(
                    conversation_payload.get(
                        "restaurant"
                    ),
                    dict,
                )
                else {}
            )
        )

        restaurant_id = (
            parse_int(
                context.restaurant_id
            )
            or parse_int(
                restaurant.get(
                    "restaurantId"
                )
            )
        )

        food_context = context

        if restaurant_id is None:
            restaurants = (
                await self.food
                .get_my_restaurants(
                    context
                )
            )

            safe_restaurants = [
                dict(item)
                for item in restaurants
                if isinstance(item, dict)
                and parse_int(
                    item.get(
                        "restaurantId"
                    )
                )
                is not None
            ]

            if len(safe_restaurants) == 1:
                restaurant = (
                    safe_restaurants[0]
                )

                restaurant_id = parse_int(
                    restaurant.get(
                        "restaurantId"
                    )
                )

            elif len(safe_restaurants) > 1:
                names = [
                    str(
                        item.get(
                            "restaurantName"
                        )
                        or (
                            "رستوران "
                            + str(
                                item.get(
                                    "restaurantId"
                                )
                            )
                        )
                    )
                    for item in (
                        safe_restaurants
                    )
                ]

                return {
                    "reply": (
                        "برای حذف یا تغییر غذا، "
                        "ابتدا رستوران را مشخص کنید: "
                        + "، ".join(names)
                    ),
                    "requiresConfirmation": False,
                    "data": {
                        "restaurants": (
                            safe_restaurants
                        ),
                    },
                }

            else:
                return {
                    "reply": (
                        "رستوران مجاز برای عملیات "
                        "غذا پیدا نشد."
                    ),
                    "requiresConfirmation": False,
                }

        if restaurant_id is None:
            return {
                "reply": (
                    "شناسه رستوران برای عملیات "
                    "غذا مشخص نیست."
                ),
                "requiresConfirmation": False,
            }

        food_context = context.model_copy(
            update={
                "restaurant_id": (
                    restaurant_id
                ),
                "meal_id": (
                    context.meal_id
                    or FOOD_MEAL_ID
                ),
            }
        )

        if not restaurant:
            restaurant = {
                "restaurantId": (
                    restaurant_id
                ),
                "restaurantName": "",
            }

        menu = await self.food.get_weekly_menu(
            food_context
        )

        days = [
            dict(day)
            for day in (
                menu.get("days")
                or []
            )
            if isinstance(day, dict)
        ]

        menu_mentions = (
            self._foods_mentioned_in_text(
                normalized,
                days,
            )
        )

        has_food_hint = any(
            word in normalized
            for word in (
                "غذا",
                "غذای",
                "رزرو",
                "ناهار",
                "منو",
            )
        )

        has_date_hint = bool(
            self._requested_weekday(
                normalized
            )
        ) or any(
            word in normalized
            for word in (
                "امروز",
                "فردا",
                "پس فردا",
                "پسفردا",
                "فروردین",
                "اردیبهشت",
                "خرداد",
                "تیر",
                "مرداد",
                "شهریور",
                "مهر",
                "آبان",
                "آذر",
                "دی",
                "بهمن",
                "اسفند",
            )
        )

        if not (
            has_food_hint
            or has_date_hint
            or menu_mentions
        ):
            return None

        target_day = (
            self._resolve_food_mutation_day(
                normalized,
                days,
                str(
                    food_context.date
                    or ""
                ),
            )
        )

        if target_day is None:
            selected_days = [
                day
                for day in days
                if parse_int(
                    day.get(
                        "selectedPlanDetailId"
                    )
                )
                not in {
                    None,
                    0,
                }
            ]

            if selected_days:
                labels = [
                    (
                        str(
                            day.get(
                                "dayOfWeek"
                            )
                            or ""
                        )
                        + " "
                        + str(
                            day.get("date")
                            or ""
                        )
                    ).strip()
                    for day in selected_days
                ]

                return {
                    "reply": (
                        "مشخص کنید رزرو کدام روز "
                        "باید حذف یا تغییر کند: "
                        + "، ".join(labels)
                    ),
                    "requiresConfirmation": False,
                    "data": {
                        "days": selected_days,
                        "restaurant": restaurant,
                    },
                }

            return {
                "reply": (
                    "رزرو فعال غذایی برای حذف "
                    "یا تغییر پیدا نشد."
                ),
                "requiresConfirmation": False,
                "data": {
                    "days": [],
                    "restaurant": restaurant,
                },
            }

        target_date = str(
            target_day.get("date")
            or ""
        ).strip()

        day_label = str(
            target_day.get(
                "dayOfWeek"
            )
            or target_date
            or "روز موردنظر"
        ).strip()

        selected_id = parse_int(
            target_day.get(
                "selectedPlanDetailId"
            )
        )

        if (
            selected_id is None
            or selected_id == 0
        ):
            return {
                "reply": (
                    f"برای {day_label} "
                    "رزرو فعالی وجود ندارد."
                ),
                "requiresConfirmation": False,
                "data": {
                    "date": target_date,
                    "dayOfWeek": day_label,
                    "days": [target_day],
                    "restaurant": restaurant,
                },
            }

        foods = [
            dict(food)
            for food in (
                target_day.get("foods")
                or []
            )
            if isinstance(food, dict)
        ]

        selected_food = next(
            (
                food
                for food in foods
                if parse_int(
                    food.get(
                        "planDetailId"
                    )
                )
                == selected_id
            ),
            {},
        )

        selected_name = str(
            selected_food.get(
                "foodName"
            )
            or "غذای رزروشده"
        ).strip()

        target_mentions = (
            self._foods_mentioned_in_text(
                normalized,
                [target_day],
            )
        )

        if mutation_kind == "cancel":
            mentioned_ids = {
                parse_int(
                    food.get(
                        "planDetailId"
                    )
                )
                for _, _, food in (
                    target_mentions
                )
            }

            mentioned_ids.discard(None)
            mentioned_ids.discard(0)

            if (
                mentioned_ids
                and selected_id
                not in mentioned_ids
            ):
                mentioned_names = [
                    str(
                        food.get(
                            "foodName"
                        )
                        or ""
                    ).strip()
                    for _, _, food in (
                        target_mentions
                    )
                    if str(
                        food.get(
                            "foodName"
                        )
                        or ""
                    ).strip()
                ]

                return {
                    "reply": (
                        f"رزرو فعلی {day_label} "
                        f"«{selected_name}» است، نه "
                        f"«{'، '.join(mentioned_names)}». "
                        "برای جلوگیری از حذف اشتباه، "
                        f"بنویسید: {selected_name} "
                        f"{day_label} را حذف کن."
                    ),
                    "requiresConfirmation": False,
                    "data": {
                        "date": target_date,
                        "dayOfWeek": day_label,
                        "food": selected_food,
                        "restaurant": restaurant,
                    },
                }

            action_payload = {
                "planDetailId": selected_id,
                "restaurantId": (
                    restaurant_id
                ),
                "mealId": (
                    food_context.meal_id
                    or FOOD_MEAL_ID
                ),
            }

            action = (
                await self.actions
                .create_pending_action(
                    str(
                        food_context.employee_id
                    ),
                    "CANCEL_FOOD",
                    action_payload,
                )
            )

            response = {
                "reply": (
                    f"رزرو «{selected_name}» "
                    f"برای {day_label} لغو شود؟"
                ),
                "requiresConfirmation": True,
                "pendingAction": {
                    "id": action["id"],
                    "label": (
                        "تأیید و لغو رزرو غذا"
                    ),
                    "expiresAt": action.get(
                        "expiresAt"
                    ),
                },
                "data": {
                    "date": target_date,
                    "dayOfWeek": day_label,
                    "food": selected_food,
                    "restaurant": restaurant,
                    "days": [target_day],
                    "mealId": (
                        food_context.meal_id
                        or FOOD_MEAL_ID
                    ),
                },
            }

            mutation_intent = (
                "CANCEL_FOOD"
            )

        else:
            available_alternatives = []

            for food in foods:
                food_id = parse_int(
                    food.get(
                        "planDetailId"
                    )
                )

                if (
                    food_id is None
                    or food_id == 0
                    or food_id
                    == selected_id
                ):
                    continue

                remain_count = parse_int(
                    food.get(
                        "remainCount"
                    )
                )

                if (
                    remain_count
                    is not None
                    and remain_count <= 0
                ):
                    continue

                available_alternatives.append(
                    food
                )

            scored_alternatives = [
                (
                    self._food_name_match_score(
                        normalized,
                        str(
                            food.get(
                                "foodName"
                            )
                            or ""
                        ),
                    ),
                    food,
                )
                for food in (
                    available_alternatives
                )
            ]

            scored_alternatives = [
                item
                for item in scored_alternatives
                if item[0] > 0
            ]

            scored_alternatives.sort(
                key=lambda item: item[0],
                reverse=True,
            )

            if not scored_alternatives:
                names = [
                    str(
                        food.get(
                            "foodName"
                        )
                        or ""
                    ).strip()
                    for food in (
                        available_alternatives
                    )
                    if str(
                        food.get(
                            "foodName"
                        )
                        or ""
                    ).strip()
                ]

                reply = (
                    f"رزرو فعلی {day_label} "
                    f"«{selected_name}» است. "
                    "نام غذای جایگزین را مشخص کنید."
                )

                if names:
                    reply += (
                        " گزینه‌های قابل رزرو: "
                        + "، ".join(names)
                        + "."
                    )

                return {
                    "reply": reply,
                    "requiresConfirmation": False,
                    "data": {
                        "date": target_date,
                        "dayOfWeek": day_label,
                        "currentFood": (
                            selected_food
                        ),
                        "alternatives": (
                            available_alternatives
                        ),
                        "restaurant": restaurant,
                        "days": [target_day],
                    },
                }

            best_score = (
                scored_alternatives[0][0]
            )

            tied = [
                food
                for score, food in (
                    scored_alternatives
                )
                if score == best_score
            ]

            if len(tied) > 1:
                tied_names = [
                    str(
                        food.get(
                            "foodName"
                        )
                        or ""
                    ).strip()
                    for food in tied
                ]

                return {
                    "reply": (
                        "چند غذای جایگزین ممکن "
                        "پیدا شد. یکی را دقیق انتخاب کنید: "
                        + "، ".join(tied_names)
                    ),
                    "requiresConfirmation": False,
                    "data": {
                        "alternatives": tied,
                        "date": target_date,
                        "restaurant": restaurant,
                    },
                }

            new_food = tied[0]

            new_id = parse_int(
                new_food.get(
                    "planDetailId"
                )
            )

            new_name = str(
                new_food.get(
                    "foodName"
                )
                or "غذای جدید"
            ).strip()

            if (
                new_id is None
                or new_id == 0
            ):
                raise AppError(
                    "شناسه غذای جایگزین معتبر نیست.",
                    code=(
                        "INVALID_NEW_PLAN_DETAIL"
                    ),
                )

            action_payload = {
                "oldPlanDetailId": (
                    selected_id
                ),
                "newPlanDetailId": new_id,
                "restaurantId": (
                    restaurant_id
                ),
                "mealId": (
                    food_context.meal_id
                    or FOOD_MEAL_ID
                ),
                "targetDate": target_date,
                "oldFoodName": (
                    selected_name
                ),
                "newFoodName": new_name,
            }

            action = (
                await self.actions
                .create_pending_action(
                    str(
                        food_context.employee_id
                    ),
                    "CHANGE_FOOD",
                    action_payload,
                )
            )

            response = {
                "reply": (
                    f"رزرو «{selected_name}» "
                    f"{day_label} لغو و "
                    f"«{new_name}» رزرو شود؟"
                ),
                "requiresConfirmation": True,
                "pendingAction": {
                    "id": action["id"],
                    "label": (
                        "تأیید و تغییر رزرو غذا"
                    ),
                    "expiresAt": action.get(
                        "expiresAt"
                    ),
                },
                "data": {
                    "date": target_date,
                    "dayOfWeek": day_label,
                    "currentFood": (
                        selected_food
                    ),
                    "newFood": new_food,
                    "restaurant": restaurant,
                    "days": [target_day],
                    "mealId": (
                        food_context.meal_id
                        or FOOD_MEAL_ID
                    ),
                },
            }

            mutation_intent = (
                "CHANGE_FOOD"
            )

        mutation_nlu = {
            "domain": "FOOD",
            "intent": mutation_intent,
            "entities": {
                "date": target_date,
            },
            "confidence": 1.0,
            "missingFields": [],
            "needsClarification": False,
            "conversationComplete": False,
            "clarification": None,
            "errors": [],
            "state": {
                "domain": "FOOD",
                "intent": mutation_intent,
                "entities": {
                    "date": target_date,
                },
                "missingFields": [],
            },
        }

        return await self._finalize_response_state(
            food_context,
            mutation_nlu,
            conversation_payload,
            response,
            normalized,
        )

    def _override_explicit_food_command(
        self,
        nlu_result: dict[str, Any],
        text: str,
        conversation_payload: dict[str, Any],
    ) -> dict[str, Any]:
        # FOOD_ROUTER_V4
        result = dict(
            nlu_result
            or {}
        )

        # FOOD_ROUTER_DOMAIN_GUARD_V1
        # An explicit non-food NLU result must
        # never be converted into a food command.
        detected_domain = str(
            result.get("domain")
            or ""
        ).strip().upper()

        if detected_domain in {
            "LEAVE",
            "MISSION",
            "ATTENDANCE",
        }:
            return result

        normalized = normalize_nlu_text(
            text
            or ""
        )

        food_candidates = (
            self._find_food_candidates(
                text,
                conversation_payload,
            )
        )

        has_candidate = bool(
            food_candidates
        )

        has_food_subject = any(
            word in normalized
            for word in [
                "غذا",
                "غذای",
                "غذاها",
                "منو",
                "ناهار",
                "خوراک",
            ]
        )

        reserve_phrases = [
            "رزرو کن",
            "رزرو شه",
            "رزرو شود",
            "ثبت کن",
            "ثبت شه",
            "ثبت شود",
            "انتخاب کن",
            "انتخاب شه",
            "انتخاب شود",
            "برام بگیر",
            "برایم بگیر",
            "سفارش بده",
        ]

        show_phrases = [
            "منو",
            "نشان بده",
            "نشون بده",
            "نشون",
            "نمایش بده",
            "لیست کن",
            "بگو",
            "چیه",
            "چی هست",
            "چه غذایی",
            "غذای امروز",
            "غذای فردا",
        ]

        cancel_phrases = [
            "لغو کن",
            "لغو شه",
            "لغو شود",
            "کنسل کن",
            "حذف کن",
        ]

        has_reserve_command = any(
            phrase in normalized
            for phrase in reserve_phrases
        )

        has_show_command = any(
            phrase in normalized
            for phrase in show_phrases
        )

        has_cancel_command = any(
            phrase in normalized
            for phrase in cancel_phrases
        )

        requested_weekday = (
            self._requested_weekday(
                text
            )
        )

        has_date_word = any(
            word in normalized
            for word in [
                "امروز",
                "فردا",
                "پس فردا",
                "پسفردا",
                "فروردین",
                "اردیبهشت",
                "خرداد",
                "تیر",
                "مرداد",
                "شهریور",
                "مهر",
                "آبان",
                "آذر",
                "دی",
                "بهمن",
                "اسفند",
            ]
        )

        last_domain_is_food = (
            str(
                conversation_payload.get(
                    "lastDomain"
                )
                or ""
            )
            == "FOOD"
        )

        food_context = (
            has_food_subject
            or has_candidate
            or last_domain_is_food
        )

        intent = None

        if (
            has_cancel_command
            and food_context
        ):
            intent = "CANCEL_FOOD"

        elif (
            has_reserve_command
            and (
                food_context
                or bool(
                    requested_weekday
                )
                or has_date_word
            )
        ):
            intent = "RESERVE_FOOD"

        elif (
            has_show_command
            and (
                has_food_subject
                or bool(
                    requested_weekday
                )
                or has_date_word
            )
        ):
            intent = "SHOW_FOOD_MENU"

        if not intent:
            return result

        entities = dict(
            result.get("entities")
            or {}
        )

        inferred_date = (
            self._infer_menu_date(
                text,
                conversation_payload,
            )
        )

        candidate_dates = {
            str(
                item.get(
                    "day",
                    {},
                ).get("date")
                or ""
            ).strip()
            for item in food_candidates
            if isinstance(
                item,
                dict,
            )
            and str(
                item.get(
                    "day",
                    {},
                ).get("date")
                or ""
            ).strip()
        }

        if (
            not inferred_date
            and len(candidate_dates) == 1
        ):
            inferred_date = next(
                iter(candidate_dates)
            )

        if inferred_date:
            entities["date"] = str(
                inferred_date
            )

        state = dict(
            result.get("state")
            or {}
        )

        state.update(
            {
                "domain": "FOOD",
                "intent": intent,
                "entities": entities,
                "missingFields": [],
            }
        )

        return {
            **result,
            "domain": "FOOD",
            "intent": intent,
            "entities": entities,
            "confidence": 0.99,
            "missingFields": [],
            "needsClarification": False,
            "conversationComplete": False,
            "clarification": None,
            "errors": [],
            "state": state,
        }

    @staticmethod
    def _is_food(text: str) -> bool:
        return any(
            keyword in text
            for keyword in [
                "غذا",
                "منو",
                "ناهار",
                "شام",
                "رزرو خوراک",
            ]
        )

    @staticmethod
    def _is_leave_balance(text: str) -> bool:
        return any(
            keyword in text
            for keyword in [
                "مانده مرخصی",
                "سهمیه مرخصی",
                "موجودی مرخصی",
            ]
        )

    @staticmethod
    def _is_leave_list(text: str) -> bool:
        read_words = [
            "نمایش",
            "نشان",
            "لیست",
            "ببین",
            "وضعیت",
            "درخواست های",
            "درخواست‌های",
        ]
        leave_words = [
            "مرخصی",
            "ماموریت",
            "مأموریت",
        ]
        mutation_words = [
            "ثبت",
            "حذف",
            "لغو",
            "کنسل",
            "بزن",
        ]
        return (
            any(
                word in text
                for word in read_words
            )
            and any(
                word in text
                for word in leave_words
            )
            and not any(
                word in text
                for word in mutation_words
            )
        )

    @staticmethod
    def _is_delete_leave(text: str) -> bool:
        return any(
            keyword in text
            for keyword in [
                "حذف",
                "کنسل",
                "لغو",
            ]
        ) and any(
            keyword in text
            for keyword in [
                "مرخصی",
                "ماموریت",
                "مأموریت",
                "درخواست",
            ]
        )

    @staticmethod
    def _is_leave_create(text: str) -> bool:
        return any(
            keyword in text
            for keyword in [
                "مرخصی",
                "ماموریت",
                "مأموریت",
                "اضافه کاری",
                "اضافه‌کاری",
            ]
        ) and any(
            keyword in text
            for keyword in [
                "ثبت",
                "درخواست",
                "بزن",
            ]
        )

    @staticmethod
    def _is_attendance(text: str) -> bool:
        return any(
            keyword in text
            for keyword in [
                "تردد",
                "ورود",
                "خروج",
                "ساعت زنی",
                "ساعت‌زنی",
            ]
        )

    async def _handle_food(
        self,
        context: AgentContext,
        text: str,
        dates: list[str],
        *,
        restaurant_validated: bool = False,
        selected_restaurant: dict[str, Any] | None = None,
        conversation_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        conversation_payload = dict(
            conversation_payload or {}
        )

        requested_weekday = (
            self._requested_weekday(text)
        )

        target_date = (
            dates[0]
            if dates
            else None
        )

        # FOOD_WEEKLY_MENU_V2
        normalized_food_text = (
            normalize_nlu_text(text)
        )

        menu_request_words = [
            "منو",
            "نشان بده",
            "نشون بده",
            "نشون",
            "نمایش",
            "لیست",
            "ببین",
            "بیار",
            "چه غذایی",
            "غذاها",
        ]

        reservation_request_words = [
            "رزرو",
            "ثبت",
            "انتخاب",
            "برام بگیر",
            "برایم بگیر",
            "بگیرش",
            "سفارش",
        ]

        relative_date_words = [
            "امروز",
            "فردا",
            "پس فردا",
            "پسفردا",
        ]

        has_explicit_numeric_date = bool(
            re.search(
                r"(?:13|14)[0-9]{2}"
                r"\s*/\s*[0-9]{1,2}"
                r"\s*/\s*[0-9]{1,2}",
                normalized_food_text,
            )
        )

        has_explicit_named_date = bool(
            re.search(
                r"[0-9۰-۹]{1,2}\s*"
                r"(?:فروردین|اردیبهشت|خرداد|"
                r"تیر|مرداد|شهریور|مهر|آبان|"
                r"آذر|دی|بهمن|اسفند)",
                normalized_food_text,
            )
        )

        has_relative_date = any(
            word in normalized_food_text
            for word in relative_date_words
        )

        is_menu_request = any(
            word in normalized_food_text
            for word in menu_request_words
        )

        is_reservation_request = any(
            word in normalized_food_text
            for word in reservation_request_words
        )

        broad_weekly_menu_request = (
            is_menu_request
            and not is_reservation_request
            and not requested_weekday
            and not has_explicit_numeric_date
            and not has_explicit_named_date
            and not has_relative_date
        )

        weekday_without_explicit_date = (
            bool(requested_weekday)
            and not has_explicit_numeric_date
            and not has_explicit_named_date
            and not has_relative_date
        )

        if (
            broad_weekly_menu_request
            or weekday_without_explicit_date
        ):
            target_date = None

        menu_cache: dict[str, Any] | None = (
            None
        )

        if any(
            keyword in text
            for keyword in [
                "امتیاز",
                "ستاره",
                "نظر غذا",
                "نظر برای غذا",
            ]
        ):
            return await self._prepare_food_rating(
                context,
                text,
            )

        if not restaurant_validated:
            return await self._begin_restaurant_selection(
                context,
                text,
                (
                    str(target_date)
                    if target_date
                    else None
                ),
                conversation_payload,
            )

        restaurant_data = (
            selected_restaurant
            or (
                conversation_payload.get(
                    "restaurant"
                )
                if isinstance(
                    conversation_payload.get(
                        "restaurant"
                    ),
                    dict,
                )
                else None
            )
            or {
                "restaurantId": (
                    context.restaurant_id
                ),
                "restaurantName": "",
            }
        )

        # FOOD_FINAL_PART2_EXACT_RESERVATION_V1
        if (
            requested_weekday
            and not has_explicit_numeric_date
            and not has_explicit_named_date
            and not has_relative_date
        ):
            menu_cache = (
                await self.food.get_weekly_menu(
                    context
                )
            )

            resolved_weekday_date = (
                self._infer_menu_date_from_days(
                    text,
                    menu_cache.get("days")
                    or [],
                )
            )

            if resolved_weekday_date:
                target_date = (
                    resolved_weekday_date
                )

        elif (
            requested_weekday
            and not target_date
        ):
            menu_cache = (
                await self.food.get_weekly_menu(
                    context
                )
            )

            target_date = (
                self._infer_menu_date_from_days(
                    text,
                    menu_cache.get("days")
                    or [],
                )
            )

        if any(
            keyword in text
            for keyword in [
                "حذف",
                "لغو",
                "کنسل",
            ]
        ):
            return await self._prepare_cancel_food(
                context,
                (
                    str(target_date)
                    if target_date
                    else None
                ),
                restaurant_data,
            )

        if any(
            keyword in text
            for keyword in [
                "رزرو من",
                "چی رزرو",
                "غذای رزرو",
                "وضعیت رزرو",
            ]
        ):
            menu = (
                menu_cache
                or await self.food.get_weekly_menu(
                    context
                )
            )
            status_days = self._filter_menu_days(
                menu.get("days") or [],
                (
                    str(target_date)
                    if target_date
                    else None
                ),
                text,
            )
            selected = [
                {
                    "date": day.get("date"),
                    "dayOfWeek": (
                        day.get("dayOfWeek")
                    ),
                    "selectedPlanDetailId": (
                        day.get(
                            "selectedPlanDetailId"
                        )
                    ),
                    "foods": (
                        day.get("foods") or []
                    ),
                }
                for day in status_days
                if day.get(
                    "selectedPlanDetailId"
                )
            ]

            return {
                "reply": (
                    self._reservation_status_reply(
                        selected
                    )
                ),
                "requiresConfirmation": False,
                "data": {
                    "restaurant": (
                        restaurant_data
                    ),
                    "reservations": selected,
                },
            }

        reservation_intent = any(
            keyword in text
            for keyword in [
                "رزرو",
                "ثبت",
                "انتخاب",
                "برام بگیر",
                "برایم بگیر",
                "بگیرش",
                "ثبتش کن",
                "ثبت شه",
                "ثبت شود",
                "انتخابش کن",
                "انتخاب شه",
                "انتخاب شود",
                "سفارش بده",
            ]
        )

        recommendation_intent = any(
            keyword in text
            for keyword in [
                "پیشنهاد",
                "چی بخور",
                "چه بخور",
                "بهترین غذا",
                "انتخاب مناسب",
            ]
        )

        menu_intent = any(
            keyword in text
            for keyword in [
                "منو",
                "نشان بده",
                "نشون بده",
                "نشون",
                "نمایش",
                "لیست",
                "ببین",
                "بیار",
                "چه غذایی",
                "غذاها",
            ]
        )

        if (
            menu_intent
            and not reservation_intent
            and not recommendation_intent
        ):
            # FOOD_RECOMMENDATION_V3
            menu = (
                await self.food
                .get_weekly_menu_insights(
                    context,
                    (
                        str(target_date)
                        if target_date
                        else None
                    ),
                    max_days=7,
                )
            )

            days = self._filter_menu_days(
                menu.get("days")
                or [],
                (
                    str(target_date)
                    if target_date
                    else None
                ),
                text,
            )

            return {
                "reply": (
                    self._menu_reply(
                        days
                    )
                ),
                "requiresConfirmation": False,
                "data": {
                    **menu,
                    "restaurant": (
                        restaurant_data
                    ),
                    "days": days,
                },
            }

        if (
            recommendation_intent
            and not reservation_intent
        ):
            recommendation = (
                await self.food.recommend_food(
                    context,
                    (
                        str(target_date)
                        if target_date
                        else None
                    ),
                )
            )

            if recommendation.get(
                "alreadyReserved"
            ):
                current = (
                    recommendation[
                        "alreadyReserved"
                    ][0]
                )

                return {
                    "reply": (
                        f"برای {current.get('date')} "
                        "قبلاً غذا رزرو شده است."
                    ),
                    "requiresConfirmation": False,
                    "data": {
                        **recommendation,
                        "restaurant": (
                            restaurant_data
                        ),
                    },
                }

            recommendations = (
                recommendation.get(
                    "recommendations"
                )
                or []
            )

            return {
                "reply": (
                    (
                        recommendations[0].get(
                            "message"
                        )
                        or "پیشنهاد غذا آماده شد."
                    )
                    if recommendations
                    else (
                        "برای تاریخ موردنظر غذای "
                        "دارای ظرفیت پیدا نشد."
                    )
                ),
                "requiresConfirmation": False,
                "data": {
                    **recommendation,
                    "restaurant": (
                        restaurant_data
                    ),
                },
            }

        if not reservation_intent:
            menu = (
                menu_cache
                or await self.food.get_weekly_menu(
                    context
                )
            )
            days = self._filter_menu_days(
                menu.get("days") or [],
                (
                    str(target_date)
                    if target_date
                    else None
                ),
                text,
            )

            return {
                "reply": (
                    self._menu_reply(days)
                    + (
                        " برای رزرو، نام غذا "
                        "را بفرستید."
                        if days
                        else ""
                    )
                ),
                "requiresConfirmation": False,
                "data": {
                    **menu,
                    "restaurant": (
                        restaurant_data
                    ),
                    "days": days,
                },
            }

        reservation_menu = (
            menu_cache
            or await self.food.get_weekly_menu(
                context
            )
        )

        reservation_days = [
            dict(day)
            for day in (
                reservation_menu.get(
                    "days"
                )
                or []
            )
            if isinstance(day, dict)
        ]

        named_candidates = (
            self._find_food_candidates_in_days(
                text,
                reservation_days,
                (
                    str(target_date)
                    if target_date
                    else None
                ),
            )
        )

        if named_candidates:
            fresh_payload = dict(
                conversation_payload
            )
            fresh_payload[
                "recentMenus"
            ] = self._merge_menu_days(
                fresh_payload.get(
                    "recentMenus"
                ),
                reservation_days,
            )

            return await self._prepare_named_food_reservation(
                context,
                text,
                named_candidates,
                (
                    str(target_date)
                    if target_date
                    else None
                ),
                restaurant_data,
                fresh_payload,
            )

        requested_food_tokens = (
            self._requested_food_tokens(
                text
            )
        )

        if requested_food_tokens:
            relevant_days = (
                self._filter_menu_days(
                    reservation_days,
                    (
                        str(target_date)
                        if target_date
                        else None
                    ),
                    text,
                )
            )

            available_names: list[str] = []

            for day in relevant_days:
                for food in (
                    day.get("foods")
                    or []
                ):
                    if not isinstance(
                        food,
                        dict,
                    ):
                        continue

                    food_name = str(
                        food.get("foodName")
                        or ""
                    ).strip()

                    remain_count = (
                        parse_int(
                            food.get(
                                "remainCount"
                            )
                        )
                    )

                    if (
                        not food_name
                        or (
                            remain_count
                            is not None
                            and remain_count <= 0
                        )
                    ):
                        continue

                    if (
                        food_name
                        not in available_names
                    ):
                        available_names.append(
                            food_name
                        )

            target_label = (
                requested_weekday
                or str(
                    target_date
                    or ""
                ).strip()
                or "بازه موردنظر"
            )

            reply = (
                "غذای نام‌برده‌شده در منوی "
                f"{target_label} پیدا نشد."
            )

            if available_names:
                reply += (
                    " گزینه‌های قابل رزرو: "
                    + "، ".join(
                        available_names[:8]
                    )
                    + "."
                )

            return {
                "reply": reply,
                "requiresConfirmation": False,
                "data": {
                    **reservation_menu,
                    "restaurant": (
                        restaurant_data
                    ),
                    "date": target_date,
                    "days": relevant_days,
                    "requestedFoodFound": (
                        False
                    ),
                },
            }

        recommendation = (
            await self.food.recommend_food(
                context,
                (
                    str(target_date)
                    if target_date
                    else None
                ),
            )
        )

        if recommendation.get(
            "alreadyReserved"
        ):
            current = (
                recommendation[
                    "alreadyReserved"
                ][0]
            )

            return {
                "reply": (
                    f"برای {current.get('date')} قبلاً "
                    "غذا رزرو شده است. ابتدا رزرو فعلی "
                    "را مشاهده یا لغو کنید."
                ),
                "requiresConfirmation": False,
                "data": {
                    **current,
                    "restaurant": (
                        restaurant_data
                    ),
                },
            }

        recommendations = (
            recommendation.get(
                "recommendations"
            )
            or []
        )

        if not recommendations:
            return {
                "reply": (
                    "برای تاریخ موردنظر غذای دارای "
                    "ظرفیت پیدا نشد."
                ),
                "requiresConfirmation": False,
                "data": {
                    "date": target_date,
                    "restaurant": (
                        restaurant_data
                    ),
                },
            }

        first = recommendations[0]
        food = first["food"]
        plan_detail_id = food.get(
            "planDetailId"
        )

        if not plan_detail_id:
            raise AppError(
                "شناسه غذای پیشنهادی از API دریافت نشد.",
                code="MISSING_PLAN_DETAIL",
            )

        action_payload = {
            "planDetailId": plan_detail_id,
            "restaurantId": (
                context.restaurant_id
            ),
            "mealId": (
                context.meal_id
                or FOOD_MEAL_ID
            ),
        }

        action = (
            await self.actions.create_pending_action(
                str(context.employee_id),
                "RESERVE_FOOD",
                action_payload,
            )
        )

        return {
            "reply": (
                first.get("message")
                or (
                    f"«{food.get('foodName') or 'غذای پیشنهادی'}» "
                    f"برای {first.get('date')} رزرو شود؟"
                )
            ),
            "requiresConfirmation": True,
            "pendingAction": {
                "id": action["id"],
                "label": "تأیید و رزرو غذا",
                "expiresAt": action.get(
                    "expiresAt"
                ),
            },
            "data": {
                "date": first.get("date"),
                "dayOfWeek": (
                    first.get("dayOfWeek")
                ),
                "food": food,
                "restaurant": (
                    restaurant_data
                ),
                "mealId": (
                    context.meal_id
                    or FOOD_MEAL_ID
                ),
            },
        }

    @staticmethod
    def _requested_weekday(
        text: str,
    ) -> str | None:
        normalized = normalize_nlu_text(
            text
        )

        aliases = {
            "شنبه": "شنبه",
            "یکشنبه": "یکشنبه",
            "یک شنبه": "یکشنبه",
            "دوشنبه": "دوشنبه",
            "دو شنبه": "دوشنبه",
            "سه شنبه": "سه شنبه",
            "سهشنبه": "سه شنبه",
            "چهارشنبه": "چهارشنبه",
            "چهار شنبه": "چهارشنبه",
            "پنجشنبه": "پنجشنبه",
            "پنج شنبه": "پنجشنبه",
            "جمعه": "جمعه",
        }

        matches: list[
            tuple[int, int, str]
        ] = []

        for alias, canonical in (
            aliases.items()
        ):
            position = normalized.rfind(
                alias
            )

            if position >= 0:
                matches.append(
                    (
                        position + len(alias),
                        len(alias),
                        canonical,
                    )
                )

        if not matches:
            return None

        return max(matches)[2]

    @classmethod
    def _infer_menu_date_from_days(
        cls,
        text: str,
        days: list[Any],
    ) -> str | None:
        requested_weekday = (
            cls._requested_weekday(text)
        )

        if not requested_weekday:
            return None

        normalized_requested = (
            normalize_nlu_text(
                requested_weekday
            ).replace(" ", "")
        )

        for day in days:
            if not isinstance(day, dict):
                continue

            day_name = (
                normalize_nlu_text(
                    day.get("dayOfWeek")
                    or ""
                ).replace(" ", "")
            )

            if (
                day_name
                and day_name
                == normalized_requested
            ):
                date_value = str(
                    day.get("date") or ""
                ).strip()
                return date_value or None

        return None

    @classmethod
    def _filter_menu_days(
        cls,
        days: list[Any],
        target_date: str | None,
        text: str,
    ) -> list[dict[str, Any]]:
        safe_days = [
            dict(day)
            for day in days
            if isinstance(day, dict)
        ]

        if target_date:
            return [
                day
                for day in safe_days
                if str(
                    day.get("date") or ""
                )
                == str(target_date)
            ]

        requested_weekday = (
            cls._requested_weekday(text)
        )

        if not requested_weekday:
            return safe_days

        normalized_requested = (
            normalize_nlu_text(
                requested_weekday
            ).replace(" ", "")
        )

        return [
            day
            for day in safe_days
            if normalize_nlu_text(
                day.get("dayOfWeek")
                or ""
            ).replace(" ", "")
            == normalized_requested
        ]

    @staticmethod
    def _menu_reply(
        days: list[dict[str, Any]],
    ) -> str:
        # FOOD_RECOMMENDATION_V3
        if not days:
            return (
                "برای تاریخ موردنظر "
                "منویی پیدا نشد."
            )

        lines: list[str] = [
            (
                "منوی این هفته:"
                if len(days) > 1
                else "منوی غذا:"
            )
        ]

        personal_best = None
        public_best = None

        for day in days:
            day_label = str(
                day.get("dayOfWeek")
                or day.get("date")
                or "این روز"
            ).strip()

            date_value = str(
                day.get("date")
                or ""
            ).strip()

            if (
                date_value
                and date_value
                not in day_label
            ):
                label = (
                    f"{day_label} "
                    f"{date_value}"
                )
            else:
                label = day_label

            foods = [
                dict(food)
                for food in (
                    day.get("foods")
                    or []
                )
                if isinstance(
                    food,
                    dict,
                )
            ]

            selected_id = str(
                day.get(
                    "selectedPlanDetailId"
                )
                or ""
            ).strip()

            lines.append("")
            lines.append(label)

            if selected_id:
                selected_name = next(
                    (
                        str(
                            food.get(
                                "foodName"
                            )
                            or ""
                        ).strip()
                        for food in foods
                        if str(
                            food.get(
                                "planDetailId"
                            )
                            or ""
                        ).strip()
                        == selected_id
                    ),
                    "",
                )

                lines.append(
                    "✅ قبلاً رزرو "
                    "کرده‌اید: "
                    + (
                        selected_name
                        or "غذای رزروشده"
                    )
                )
                continue

            available_count = 0

            for food in foods:
                food_name = str(
                    food.get("foodName")
                    or ""
                ).strip()

                if not food_name:
                    continue

                remain_count = parse_int(
                    food.get(
                        "remainCount"
                    )
                )

                if (
                    remain_count
                    is not None
                    and remain_count <= 0
                ):
                    continue

                available_count += 1

                details = [
                    f"• {food_name}"
                ]

                interest = food.get(
                    "personalInterestPercent"
                )

                if interest is None:
                    details.append(
                        "علاقه شما: "
                        "سابقه کافی نیست"
                    )
                else:
                    details.append(
                        "علاقه شما: "
                        f"{int(interest)}٪"
                    )

                public_percent = food.get(
                    "publicReservationPercent"
                )

                if (
                    public_percent is not None
                    and int(public_percent) > 0
                ):
                    details.append(
                        "رزرو عمومی: "
                        f"{int(public_percent)}٪ "
                        "از ظرفیت"
                    )

                average_rate = food.get(
                    "averageRate"
                )

                vote_count = (
                    parse_int(
                        food.get(
                            "voteCount"
                        )
                    )
                    or 0
                )

                if (
                    average_rate is not None
                    and vote_count > 0
                ):
                    try:
                        rate_text = (
                            f"{float(average_rate):g}"
                        )
                    except (
                        TypeError,
                        ValueError,
                    ):
                        rate_text = str(
                            average_rate
                        )

                    rating_text = (
                        "امتیاز عمومی: "
                        f"{rate_text} از ۵"
                    )

                    if vote_count:
                        rating_text += (
                            f" ({vote_count} رأی)"
                        )

                    details.append(
                        rating_text
                    )

                # FOOD_FINAL_PART3_SAFE_MENU_LABEL_V1
                if (
                    food.get(
                        "isRecommended"
                    )
                    and (
                        parse_int(
                            interest
                        )
                        or 0
                    ) > 0
                ):
                    details.append(
                        "⭐ پیشنهاد برای شما"
                    )

                    personal_best = {
                        "name": food_name,
                        "date": date_value,
                        "day": day_label,
                        "interest": interest,
                    }

                if (
                    food.get(
                        "isPublicFavorite"
                    )
                    and (
                        (
                            public_percent
                            is not None
                            and int(
                                public_percent
                            ) > 0
                        )
                        or vote_count > 0
                    )
                ):
                    details.append(
                        "🔥 محبوب‌ترین انتخاب عمومی"
                    )

                    public_best = {
                        "name": food_name,
                        "date": date_value,
                        "day": day_label,
                        "publicPercent": (
                            public_percent
                        ),
                        "averageRate": (
                            average_rate
                        ),
                        "voteCount": (
                            vote_count
                        ),
                    }

                lines.append(
                    " — ".join(
                        details
                    )
                )

            if not available_count:
                lines.append(
                    "• غذای قابل رزروی "
                    "اعلام نشده است."
                )

        if personal_best:
            lines.extend(
                [
                    "",
                    (
                        "⭐ پیشنهاد شخصی هفته: "
                        f"{personal_best['name']} "
                        f"برای "
                        f"{personal_best['day']} "
                        f"{personal_best['date']}"
                    ).strip(),
                ]
            )

        if public_best:
            public_parts = [
                (
                    "🔥 محبوب‌ترین غذای "
                    "قابل رزرو: "
                    f"{public_best['name']}"
                )
            ]

            if (
                public_best[
                    "publicPercent"
                ]
                is not None
                and int(
                    public_best[
                        "publicPercent"
                    ]
                ) > 0
            ):
                public_parts.append(
                    (
                        f"{int(public_best['publicPercent'])}"
                        "٪ ظرفیت آن رزرو شده"
                    )
                )

            if (
                public_best[
                    "averageRate"
                ]
                is not None
                and int(
                    public_best.get(
                        "voteCount"
                    )
                    or 0
                ) > 0
            ):
                try:
                    public_rate = (
                        f"{float(public_best['averageRate']):g}"
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    public_rate = str(
                        public_best[
                            "averageRate"
                        ]
                    )

                public_parts.append(
                    (
                        "امتیاز متوسط "
                        f"{public_rate} از ۵"
                    )
                )

            lines.extend(
                [
                    "",
                    " — ".join(
                        public_parts
                    ),
                ]
            )

        return "\n".join(lines)

    @staticmethod
    def _reservation_status_reply(
        selected: list[dict[str, Any]],
    ) -> str:
        if not selected:
            return (
                "رزرو فعالی برای تاریخ "
                "موردنظر پیدا نشد."
            )

        lines = [
            f"{len(selected)} رزرو فعال پیدا شد:"
        ]

        for item in selected:
            label = str(
                item.get("dayOfWeek")
                or item.get("date")
                or "این روز"
            )
            selected_id = str(
                item.get(
                    "selectedPlanDetailId"
                )
                or ""
            )
            food_name = next(
                (
                    str(
                        food.get("foodName")
                        or ""
                    ).strip()
                    for food in (
                        item.get("foods") or []
                    )
                    if isinstance(food, dict)
                    and str(
                        food.get(
                            "planDetailId"
                        )
                    )
                    == selected_id
                ),
                "",
            )
            lines.append(
                f"- {label}: "
                f"{food_name or 'غذای رزروشده'}"
            )

        return "\n".join(lines)

    @staticmethod
    def _food_query_tokens(
        text: str,
    ) -> set[str]:
        normalized = normalize_nlu_text(
            text
        )
        tokens = set(
            re.findall(
                r"[a-zA-Z]+|[0-9]+|"
                r"[\u0600-\u06FF]+",
                normalized,
            )
        )

        stop_words = {
            "غذا",
            "غذای",
            "رزرو",
            "کن",
            "کنم",
            "بده",
            "بگیر",
            "بگیرم",
            "برام",
            "برایم",
            "برای",
            "رو",
            "را",
            "لطفا",
            "لطفاً",
            "میخوام",
            "میخواهم",
            "سفارش",
            "ثبت",
            "امروز",
            "فردا",
            "پس",
            "این",
            "هفته",
        }

        return {
            token
            for token in tokens
            if token not in stop_words
            and not token.isdigit()
            and len(token) >= 2
        }

    @staticmethod
    def _requested_food_tokens(
        text: str,
    ) -> set[str]:
        normalized = normalize_nlu_text(
            text
        )

        tokens = set(
            re.findall(
                r"[a-zA-Z]+|[0-9]+|"
                r"[\u0600-\u06FF]+",
                normalized,
            )
        )

        stop_words = {
            "غذا",
            "غذای",
            "غذاها",
            "منو",
            "ناهار",
            "خوراک",
            "رستوران",
            "رزرو",
            "ثبت",
            "انتخاب",
            "سفارش",
            "کن",
            "کنم",
            "کنید",
            "شه",
            "شود",
            "بشه",
            "بده",
            "بگیر",
            "بگیرش",
            "برام",
            "برایم",
            "برای",
            "رو",
            "را",
            "لطفا",
            "لطفاً",
            "میخوام",
            "میخواهم",
            "می",
            "خواهم",
            "امروز",
            "فردا",
            "پس",
            "پسفردا",
            "این",
            "هفته",
            "بعد",
            "شنبه",
            "یکشنبه",
            "دوشنبه",
            "سه",
            "سهشنبه",
            "چهارشنبه",
            "چهار",
            "پنجشنبه",
            "پنج",
            "جمعه",
            "فروردین",
            "اردیبهشت",
            "خرداد",
            "تیر",
            "مرداد",
            "شهریور",
            "مهر",
            "آبان",
            "آذر",
            "دی",
            "بهمن",
            "اسفند",
        }

        return {
            token
            for token in tokens
            if token not in stop_words
            and not token.isdigit()
            and len(token) >= 2
        }

    @classmethod
    def _find_food_candidates_in_days(
        cls,
        text: str,
        days: list[Any],
        target_date: str | None = None,
    ) -> list[dict[str, Any]]:
        normalized_text = normalize_nlu_text(
            text
        )

        query_tokens = (
            cls._requested_food_tokens(
                text
            )
        )

        if not query_tokens:
            return []

        safe_target_date = str(
            target_date or ""
        ).strip()

        candidates: list[
            dict[str, Any]
        ] = []

        for day in days:
            if not isinstance(day, dict):
                continue

            day_date = str(
                day.get("date") or ""
            ).strip()

            if (
                safe_target_date
                and day_date
                != safe_target_date
            ):
                continue

            for food in day.get(
                "foods"
            ) or []:
                if not isinstance(food, dict):
                    continue

                food_name = str(
                    food.get("foodName")
                    or ""
                ).strip()

                if not food_name:
                    continue

                normalized_name = (
                    normalize_nlu_text(
                        food_name
                    )
                )

                name_tokens = set(
                    re.findall(
                        r"[a-zA-Z]+|[0-9]+|"
                        r"[\u0600-\u06FF]+",
                        normalized_name,
                    )
                )

                exact_match = bool(
                    normalized_name
                    and normalized_name
                    in normalized_text
                )

                overlap = (
                    query_tokens
                    & name_tokens
                )

                token_match = bool(
                    overlap
                    and (
                        query_tokens
                        <= name_tokens
                        or name_tokens
                        <= query_tokens
                        or len(overlap) >= 2
                    )
                )

                if not (
                    exact_match
                    or token_match
                ):
                    continue

                score = (
                    100
                    if exact_match
                    else 0
                )

                score += len(overlap) * 10

                if (
                    query_tokens
                    <= name_tokens
                ):
                    score += 5

                candidates.append(
                    {
                        "day": dict(day),
                        "food": dict(food),
                        "score": score,
                    }
                )

        candidates.sort(
            key=lambda item: (
                int(
                    item.get("score")
                    or 0
                ),
                str(
                    item.get(
                        "day",
                        {},
                    ).get("date")
                    or ""
                ),
            ),
            reverse=True,
        )

        return candidates

    def _find_food_candidates(
        self,
        text: str,
        conversation_payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        query_tokens = self._food_query_tokens(
            text
        )

        if not query_tokens:
            return []

        recent_menus = (
            conversation_payload.get(
                "recentMenus"
            )
            or []
        )

        candidates: list[
            dict[str, Any]
        ] = []

        for day in recent_menus:
            if not isinstance(day, dict):
                continue

            for food in day.get(
                "foods"
            ) or []:
                if not isinstance(food, dict):
                    continue

                food_name = str(
                    food.get("foodName")
                    or ""
                ).strip()

                if not food_name:
                    continue

                normalized_name = (
                    normalize_nlu_text(
                        food_name
                    )
                )
                name_tokens = set(
                    re.findall(
                        r"[a-zA-Z]+|[0-9]+|"
                        r"[\u0600-\u06FF]+",
                        normalized_name,
                    )
                )

                overlap = (
                    query_tokens
                    & name_tokens
                )

                if (
                    normalized_name
                    in normalize_nlu_text(
                        text
                    )
                    or overlap
                ):
                    candidates.append(
                        {
                            "day": dict(day),
                            "food": dict(food),
                            "score": (
                                len(overlap)
                                + (
                                    2
                                    if normalized_name
                                    in normalize_nlu_text(
                                        text
                                    )
                                    else 0
                                )
                            ),
                        }
                    )

        candidates.sort(
            key=lambda item: (
                int(item.get("score") or 0),
                str(
                    item.get("day", {}).get(
                        "date"
                    )
                    or ""
                ),
            ),
            reverse=True,
        )

        return candidates

    async def _prepare_named_food_reservation(
        self,
        context: AgentContext,
        text: str,
        candidates: list[dict[str, Any]],
        target_date: str | None,
        restaurant: dict[str, Any],
        conversation_payload: dict[str, Any],
    ) -> dict[str, Any]:
        inferred_date = (
            self._infer_menu_date(
                text,
                conversation_payload,
            )
        )
        preferred_date = (
            target_date
            or inferred_date
            or str(
                conversation_payload.get(
                    "activeDate"
                )
                or ""
            ).strip()
            or None
        )

        preferred_candidates = [
            item
            for item in candidates
            if (
                not preferred_date
                or str(
                    item.get(
                        "day",
                        {},
                    ).get("date")
                    or ""
                )
                == preferred_date
            )
        ]

        if not preferred_candidates:
            if preferred_date:
                return {
                    "reply": (
                        "غذای نام‌برده‌شده برای "
                        f"{preferred_date} پیدا نشد."
                    ),
                    "requiresConfirmation": False,
                    "data": {
                        "date": preferred_date,
                        "restaurant": restaurant,
                        "requestedFoodFound": False,
                    },
                }

            preferred_candidates = (
                candidates
            )

        best_score = max(
            int(
                item.get("score") or 0
            )
            for item in preferred_candidates
        )
        best_candidates = [
            item
            for item in preferred_candidates
            if int(
                item.get("score") or 0
            )
            == best_score
        ]

        distinct_ids = {
            str(
                item.get("food", {}).get(
                    "planDetailId"
                )
                or ""
            )
            for item in best_candidates
        }

        if (
            len(best_candidates) > 1
            and len(distinct_ids) > 1
            and all(
                str(
                    item.get("day", {}).get(
                        "date"
                    )
                    or ""
                )
                == str(
                    best_candidates[0].get(
                        "day",
                        {},
                    ).get("date")
                    or ""
                )
                for item in best_candidates
            )
        ):
            names = [
                str(
                    item.get("food", {}).get(
                        "foodName"
                    )
                    or "غذا"
                )
                for item in best_candidates
            ]

            return {
                "reply": (
                    "چند غذای مشابه پیدا شد: "
                    + "، ".join(names)
                    + ". نام دقیق غذا را بفرستید."
                ),
                "requiresConfirmation": False,
                "data": {
                    "candidates": (
                        best_candidates
                    ),
                    "restaurant": restaurant,
                },
            }

        selected = best_candidates[0]
        day = selected["day"]
        food = selected["food"]

        plan_detail_id = food.get(
            "planDetailId"
        )

        if not plan_detail_id:
            raise AppError(
                "شناسه غذای انتخاب‌شده از API دریافت نشد.",
                code="MISSING_PLAN_DETAIL",
            )

        selected_plan_detail_id = (
            day.get(
                "selectedPlanDetailId"
            )
        )

        if selected_plan_detail_id:
            if str(
                selected_plan_detail_id
            ) == str(plan_detail_id):
                return {
                    "reply": (
                        "این غذا قبلاً برای "
                        "این روز رزرو شده است."
                    ),
                    "requiresConfirmation": False,
                    "data": {
                        "date": day.get(
                            "date"
                        ),
                        "food": food,
                        "restaurant": restaurant,
                    },
                }

            return {
                "reply": (
                    "برای این روز قبلاً غذای "
                    "دیگری رزرو شده است."
                ),
                "requiresConfirmation": False,
                "data": {
                    "date": day.get("date"),
                    "food": food,
                    "restaurant": restaurant,
                },
            }

        remain_count = parse_int(
            food.get("remainCount")
        )

        if (
            remain_count is not None
            and remain_count <= 0
        ):
            return {
                "reply": (
                    "ظرفیت این غذا تمام شده است."
                ),
                "requiresConfirmation": False,
                "data": {
                    "date": day.get("date"),
                    "food": food,
                    "restaurant": restaurant,
                },
            }

        action = (
            await self.actions.create_pending_action(
                str(context.employee_id),
                "RESERVE_FOOD",
                {
                    "planDetailId": (
                        plan_detail_id
                    ),
                    "restaurantId": (
                        context.restaurant_id
                    ),
                    "mealId": (
                        context.meal_id
                        or FOOD_MEAL_ID
                    ),
                },
            )
        )

        day_label = str(
            day.get("dayOfWeek")
            or day.get("date")
            or "این روز"
        )
        food_name = str(
            food.get("foodName")
            or "این غذا"
        )

        same_food_dates = {
            str(
                item.get("day", {}).get(
                    "date"
                )
                or ""
            )
            for item in candidates
            if normalize_nlu_text(
                item.get("food", {}).get(
                    "foodName"
                )
                or ""
            )
            == normalize_nlu_text(
                food_name
            )
        }

        if len(
            {
                value
                for value in same_food_dates
                if value
            }
        ) > 1:
            reply = (
                f"منظورتان «{food_name}» "
                f"{day_label} است؟ "
                f"برای {day_label} رزرو کنم؟"
            )
        else:
            reply = (
                f"«{food_name}» را برای "
                f"{day_label} رزرو کنم؟"
            )

        return {
            "reply": reply,
            "requiresConfirmation": True,
            "pendingAction": {
                "id": action["id"],
                "label": (
                    "تأیید و رزرو غذا"
                ),
                "expiresAt": action.get(
                    "expiresAt"
                ),
            },
            "data": {
                "date": day.get("date"),
                "dayOfWeek": (
                    day.get("dayOfWeek")
                ),
                "food": food,
                "restaurant": restaurant,
                "mealId": (
                    context.meal_id
                    or FOOD_MEAL_ID
                ),
            },
        }

    async def _prepare_cancel_food(
        self,
        context: AgentContext,
        target_date: str | None,
        restaurant: dict[str, Any],
    ) -> dict[str, Any]:
        menu = await self.food.get_weekly_menu(
            context
        )

        for day in menu.get("days") or []:
            if (
                target_date
                and day.get("date") != target_date
            ):
                continue

            selected = day.get(
                "selectedPlanDetailId"
            )

            if selected:
                action_payload = {
                    "planDetailId": selected,
                    "restaurantId": (
                        context.restaurant_id
                    ),
                    "mealId": (
                        context.meal_id
                        or FOOD_MEAL_ID
                    ),
                }

                action = (
                    await self.actions
                    .create_pending_action(
                        str(context.employee_id),
                        "CANCEL_FOOD",
                        action_payload,
                    )
                )

                return {
                    "reply": (
                        f"حذف رزرو غذا برای "
                        f"{day.get('date')} آماده شد. "
                        "پس از تأیید، حذف واقعی "
                        "انجام می‌شود."
                    ),
                    "requiresConfirmation": True,
                    "pendingAction": {
                        "id": action["id"],
                        "label": (
                            "تأیید و حذف رزرو غذا"
                        ),
                        "expiresAt": action.get(
                            "expiresAt"
                        ),
                    },
                    "data": {
                        "date": day.get("date"),
                        "selectedPlanDetailId": (
                            selected
                        ),
                        "restaurant": restaurant,
                    },
                }

        return {
            "reply": (
                "برای تاریخ گفته‌شده رزرو غذایی "
                "پیدا نشد."
            ),
            "requiresConfirmation": False,
            "data": {
                "date": target_date,
                "restaurant": restaurant,
            },
        }

    async def _prepare_food_rating(
        self,
        context: AgentContext,
        text: str,
    ) -> dict[str, Any]:
        rate_match = re.search(
            r"امتیاز\s*[:：]?\s*([1-5])"
            r"(?:\s*از\s*5)?",
            text,
        )

        if rate_match is None:
            rate_match = re.search(
                r"([1-5])\s*ستاره",
                text,
            )

        rate = (
            parse_int(rate_match.group(1))
            if rate_match
            else None
        )

        if rate is None:
            return {
                "reply": (
                    "امتیاز را بین ۱ تا ۵ وارد کنید؛ "
                    "مثلاً «به غذای آخر ۵ ستاره بده»."
                ),
                "requiresConfirmation": False,
            }

        reserve_match = re.search(
            r"(?:رزرو|شناسه)\s*(\d+)",
            text,
        )
        reserve_id = (
            parse_int(reserve_match.group(1))
            if reserve_match
            else None
        )

        history = await self.food.get_history(
            context
        )

        if reserve_id is None:
            reserve_id = next(
                (
                    parse_int(
                        item.get("reserveId")
                    )
                    for item in history
                    if parse_int(
                        item.get("reserveId")
                    )
                ),
                None,
            )

        if reserve_id is None:
            return {
                "reply": (
                    "رزرو قابل امتیازدهی پیدا نشد."
                ),
                "requiresConfirmation": False,
            }

        comment_match = re.search(
            r"(?:نظر|کامنت)\s*[:：]?\s*(.+)$",
            text,
        )
        comment = (
            comment_match.group(1).strip()
            if comment_match
            else ""
        )

        action = (
            await self.actions.create_pending_action(
                str(context.employee_id),
                "RATE_FOOD",
                {
                    "reserveId": reserve_id,
                    "rate": rate,
                    "comment": comment,
                    "isAnonymous": (
                        "ناشناس" in text
                    ),
                },
            )
        )

        return {
            "reply": (
                f"ثبت امتیاز {rate} از ۵ برای "
                f"رزرو {reserve_id} آماده شد. "
                "تأیید می‌کنید؟"
            ),
            "requiresConfirmation": True,
            "pendingAction": {
                "id": action["id"],
                "label": "تأیید و ثبت امتیاز",
                "expiresAt": action.get(
                    "expiresAt"
                ),
            },
        }

    async def _prepare_delete_leave(
        self,
        context: AgentContext,
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
            await self.hr.get_leave_requests(
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

        leave_types = await self.hr.get_leave_types(
            context
        )
        type_rows = leave_types.get("data") or []

        matched = self.hr.find_leave_type(
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
                row.get("isDeletable")
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
                    "candidateCount": (
                        len(candidates)
                    ),
                    "deletableCount": (
                        len(deletable)
                    ),
                },
            }

        row = deletable[0]

        payload = {
            "requestID": row.get("requestID"),
            "changeStateID": row.get(
                "changeStateID"
            ),
            "leaveKey": row.get("leaveKey"),
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
            await self.actions.create_pending_action(
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

    async def _prepare_create_leave(
        self,
        context: AgentContext,
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
                    "برای ثبت درخواست، تاریخ "
                    "لازم است."
                ),
                "requiresConfirmation": False,
            }

        leave_types = await self.hr.get_leave_types(
            context
        )
        type_rows = leave_types.get("data") or []

        leave_type = self.hr.find_leave_type(
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
            start_date, end_date = (
                validate_jalali_range(
                    start_date,
                    end_date,
                )
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
            "additionalValues": (
                self._extract_additional_values(
                    text,
                    leave_type,
                )
            ),
        }

        existing = (
            await self.hr.get_leave_requests(
                context,
                start_date,
            )
        )
        existing_rows = (
            existing.get("data") or []
        )

        action = (
            await self.actions.create_pending_action(
                str(context.employee_id),
                "CREATE_LEAVE",
                payload,
            )
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
                    if isinstance(
                        existing_rows,
                        list,
                    )
                    else 0
                ),
            },
        }

    # ATTENDANCE_FUTURE_CHAT_GUARD_V1
    async def _handle_future_attendance_guard(
        self,
        context: AgentContext,
        nlu_result: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not isinstance(
            nlu_result,
            dict,
        ):
            return None

        domain = str(
            nlu_result.get(
                "domain"
            )
            or ""
        )

        intent = str(
            nlu_result.get(
                "intent"
            )
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
            nlu_result.get(
                "entities"
            )
            if isinstance(
                nlu_result.get(
                    "entities"
                ),
                dict,
            )
            else {}
        )

        event_date = (
            entities.get("date")
            or entities.get(
                "eventDate"
            )
        )

        event_time = (
            entities.get("time")
            or entities.get(
                "startTime"
            )
            or entities.get(
                "endTime"
            )
        )

        reason = (
            self.actions
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

        # No incomplete attendance conversation or
        # pending-action reference must survive.
        await self._delete_conversation_state(
            context
        )

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
    async def _handle_attendance(
        self,
        context: AgentContext,
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
            handler_future_response = (
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

            if handler_future_response is not None:
                return handler_future_response

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

            events = await self.hr.get_time_events(
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

        events = await self.hr.get_time_events(
            context,
            target_dates[0],
            target_dates[0],
        )
        rows = events.get("data") or []

        valid, existing = (
            self.hr.validate_time_event_distance(
                (
                    rows
                    if isinstance(rows, list)
                    else []
                ),
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
            await self.actions.create_pending_action(
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
                f"{self._human_time(times[0])} "
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

    @staticmethod
    def _human_time(
        value: str,
    ) -> str:
        match = re.fullmatch(
            r"(\d{2}):(\d{2})",
            str(value or "").strip(),
        )

        if not match:
            return str(value)

        hour = int(match.group(1))
        minute = int(match.group(2))

        if hour == 0:
            display_hour = 12
            period = "بامداد"
        elif hour < 12:
            display_hour = hour
            period = "صبح"
        elif hour == 12:
            display_hour = 12
            period = "ظهر"
        else:
            display_hour = hour - 12
            period = "شب"

        if minute:
            return (
                f"{display_hour}:{minute:02d} "
                f"{period}"
            )

        return f"{display_hour} {period}"

    @staticmethod
    def _extract_additional_values(
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
                or str(key).upper()
                == "CUSTOMER02"
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

    @classmethod
    def _help_response(
        cls,
    ) -> dict[str, Any]:
        return {
            "reply": (
                "قابلیت‌ها: نمایش و رزرو غذا، لغو رزرو، "
                "امتیازدهی، مانده و درخواست‌های مرخصی، "
                "ثبت/حذف مرخصی و مأموریت، نمایش/ثبت "
                "تردد و گزارش روزانه. تمام عملیات "
                "تغییردهنده فقط بعد از تأیید اجرا می‌شوند."
            ),
            "requiresConfirmation": False,
            "suggestions": cls._suggestions(),
        }

    @staticmethod
    def _suggestions() -> list[str]:
        return [
            "منوی غذای امروز را نشان بده",
            "برای امروز غذا پیشنهاد بده و رزرو کن",
            "مانده مرخصی من چقدر است؟",
            "درخواست‌های مرخصی امروز را نشان بده",
            "ثبت مرخصی ساعتی امروز از 14:00 تا 17:00",
            "تردد امروز را نشان بده",
            "گزارش امروز من را بساز",
        ]