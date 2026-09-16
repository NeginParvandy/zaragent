from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from pathlib import Path
from dataclasses import is_dataclass, replace
from typing import Any

from fastapi import APIRouter, Depends

from app.api.dependencies import (
    GatewayIdentity,
    require_user_identity,
)
from app.application.container import get_container
from app.core.response import ok
from app.core.time import local_now
from app.domain.models import (
    ActionStatusRequest,
    AgentContext,
    ApiResponse,
    CancelActionRequest,
    ChatRequest,
    ConfirmActionRequest,
    DailyBriefRequest,
    ReminderCheckRequest,
    ReminderListRequest,
)

from app.core.exceptions import IntegrationError

logger = logging.getLogger(__name__)


_PILOT_HR_OVERRIDE_PATH = Path(
    r"D:\serviceAi\pilot_hr_override.json"
)


def _copy_with_update(value, changes):
    model_copy = getattr(
        value,
        "model_copy",
        None,
    )

    if callable(model_copy):
        return model_copy(
            update=changes
        )

    copy_method = getattr(
        value,
        "copy",
        None,
    )

    if callable(copy_method):
        try:
            return copy_method(
                update=changes
            )
        except TypeError:
            pass

    if is_dataclass(value):
        return replace(
            value,
            **changes,
        )

    for key, item in changes.items():
        setattr(
            value,
            key,
            item,
        )

    return value


def _apply_pilot_hr_override(context):
    try:
        config = json.loads(
            _PILOT_HR_OVERRIDE_PATH.read_text(
                encoding="utf-8"
            )
        )
    except FileNotFoundError:
        return context
    except Exception:
        logger.exception(
            "PILOT_HR_OVERRIDE_INVALID_FILE"
        )
        return context

    if config.get("enabled") is not True:
        return context

    configured_employee_id = str(
        config.get(
            "employeeId",
            "",
        )
    ).strip()

    current_employee_id = str(
        context.employee_id or ""
    ).strip()

    if (
        not configured_employee_id
        or configured_employee_id
        != current_employee_id
    ):
        return context

    # PILOT_HR_OVERRIDE_SCOPE_V1
    # Only the legacy .NET pilot bridge uses the fixed
    # credentials stored in pilot_hr_override.json.
    # Direct Swagger calls keep the session sent in Request.
    # PILOT_CONVERSATION_CONFIG_V1
    configured_conversation_id = str(
        config.get(
            "conversationId",
            "pilot-05000602",
        )
        or "pilot-05000602"
    ).strip()

    conversation_id = str(
        context.conversation_id or ""
    ).strip()

    if (
        conversation_id
        != configured_conversation_id
    ):
        logger.info(
            (
                "PILOT_HR_OVERRIDE_SKIPPED "
                "employee_id=%s "
                "reason=non_bridge_conversation"
            ),
            current_employee_id,
        )
        return context

    authorization_token = str(
        config.get(
            "authorizationToken",
            "",
        )
    ).strip()

    username_hash = str(
        config.get(
            "usernameHash",
            "",
        )
    ).strip()

    password_hash = str(
        config.get(
            "passwordHash",
            "",
        )
    ).strip()

    digit_code = config.get(
        "digitCode"
    )

    if not all(
        (
            authorization_token,
            username_hash,
            password_hash,
            digit_code is not None,
        )
    ):
        logger.error(
            (
                "PILOT_HR_OVERRIDE_SKIPPED "
                "employee_id=%s reason=incomplete_config"
            ),
            current_employee_id,
        )
        return context

    session = context.session

    if session is None:
        logger.error(
            (
                "PILOT_HR_OVERRIDE_SKIPPED "
                "employee_id=%s reason=no_session"
            ),
            current_employee_id,
        )
        return context

    updated_session = _copy_with_update(
        session,
        {
            "authorization_token": authorization_token,
            "username_hash": username_hash,
            "password_hash": password_hash,
            "digit_code": int(digit_code),
        },
    )

    updated_context = _copy_with_update(
        context,
        {
            "session": updated_session,
        },
    )

    logger.warning(
        (
            "PILOT_HR_OVERRIDE_APPLIED "
            "employee_id=%s"
        ),
        current_employee_id,
    )

    return updated_context


router = APIRouter(
    prefix="/api/agent",
    tags=["Agent"],
)


def _fallback_conversation_id(
    context: AgentContext,
    identity: GatewayIdentity,
) -> str | None:
    """
    Build a stable conversation id for legacy callers that do not
    send conversationId (for example the current .NET bridge).

    The raw token is never stored. Only a short SHA-256 digest is
    used, so two requests from the same login session share state
    while different sessions stay isolated.
    """
    employee_id = str(context.employee_id or "").strip()
    if employee_id == "05000602":
        return "pilot-05000602"

    token = str(
        identity.authorization_token or ""
    ).strip()

    if (
        not token
        and context.session is not None
        and context.session.authorization_token is not None
    ):
        token = (
            context.session.authorization_token
            .get_secret_value()
            .strip()
        )

    if token.lower().startswith("bearer "):
        token = token[7:].strip()

    if token:
        digest = hashlib.sha256(
            token.encode("utf-8")
        ).hexdigest()[:32]
        return f"bridge-{digest}"

    employee_id = str(
        context.employee_id or ""
    ).strip()

    if employee_id:
        return f"employee-{employee_id}"

    return None


@router.get(
    "/live",
    response_model=ApiResponse[dict[str, Any]],
)
async def live() -> dict[str, Any]:
    return ok(
        {
            "status": "ok",
        },
        "سرویس فعال است.",
    )


@router.get(
    "/ready",
    response_model=ApiResponse[dict[str, Any]],
)
async def ready() -> dict[str, Any]:
    container = get_container()

    database = await asyncio.to_thread(
        container.repository.health_check
    )

    return ok(
        {
            "status": "ready",
            "database": database,
        },
        "سرویس آماده پاسخ‌گویی است.",
    )


@router.get(
    "/health",
    response_model=ApiResponse[dict[str, Any]],
)
async def health(
    identity: GatewayIdentity = Depends(
        require_user_identity
    ),
) -> dict[str, Any]:
    container = get_container()

    database = await asyncio.to_thread(
        container.repository.health_check
    )

    return ok(
        {
            "status": "ok",
            "service": container.settings.app_name,
            "version": container.settings.app_version,
            "mode": "real-api-only-no-fallback",
            "authenticated": identity.authenticated,
            "database": database,
            "serverLocalTime": local_now(
                container.settings.app_timezone
            ).isoformat(),
        },
        "وضعیت سرویس دریافت شد.",
    )


@router.get(
    "/capabilities",
    response_model=ApiResponse[dict[str, Any]],
)
async def capabilities(
    _: GatewayIdentity = Depends(
        require_user_identity
    ),
) -> dict[str, Any]:
    return ok(
        {
            "dailyBrief": True,
            "reminderEngine": True,
            "chat": True,
            "actionConfirmation": True,
            "food": {
                "menu": True,
                "reserve": True,
                "cancelReservation": True,
                "ratingAndComments": True,
                "recommendation": True,
            },
            "hr": {
                "leaveRequests": True,
                "leaveCreate": True,
                "leaveDelete": True,
                "attendanceRead": True,
                "attendanceCreate": True,
            },
            "runtimeMode": "no-mock-no-fallback",
        }
    )


@router.post(
    "/daily-brief",
    response_model=ApiResponse[dict[str, Any]],
)
async def daily_brief(
    request: DailyBriefRequest,
    identity: GatewayIdentity = Depends(
        require_user_identity
    ),
) -> dict[str, Any]:
    container = get_container()

    context = container.context_resolver.resolve(
        request.to_context(),
        identity,
    )

    container.context_resolver.require_employee(
        context
    )

    data = await container.daily_brief_service.build(
        context
    )

    return ok(
        data,
        "گزارش روزانه ساخته شد.",
    )


@router.post(
    "/reminders/check",
    summary="بررسی و ایجاد یادآوری‌ها",
    description=(
        "در اولین ورود کاربر در هر روز، وضعیت غذا، تردد، "
        "مرخصی و پایان ماه را بررسی می‌کند و یادآوری‌های "
        "لازم را فقط یک بار به اپلیکیشن تحویل می‌دهد."
    ),
    response_model=ApiResponse[dict[str, Any]],
)
async def check_reminders(
    request: ReminderCheckRequest,
    identity: GatewayIdentity = Depends(
        require_user_identity
    ),
) -> dict[str, Any]:
    container = get_container()

    context = container.context_resolver.resolve(
        request.to_context(),
        identity,
    )

    container.context_resolver.require_employee(
        context
    )

    data = await container.reminder_service.check(
        context
    )

    return ok(
        data,
        (
            "وضعیت یادآوری‌های روزانه بررسی شد."
        ),
    )


@router.post(
    "/reminders",
    summary="دریافت یادآوری‌های فعال",
    description=(
        "یادآوری‌های فعال کاربر را برمی‌گرداند. "
        "وضعیت Reminder داخلی است و در Request ارسال نمی‌شود."
    ),
    response_model=ApiResponse[list[dict[str, Any]]],
)
async def list_reminders(
    request: ReminderListRequest,
    identity: GatewayIdentity = Depends(
        require_user_identity
    ),
) -> dict[str, Any]:
    container = get_container()

    context = container.context_resolver.resolve(
        request.to_context(),
        identity,
    )

    employee_id = (
        container.context_resolver.require_employee(
            context
        )
    )

    data = await container.reminder_service.list_reminders(
        employee_id
    )

    return ok(
        data,
        "لیست یادآوری‌ها دریافت شد.",
    )


@router.post(
    "/chat",
    response_model=ApiResponse[dict[str, Any]],
)
async def chat(
    request: ChatRequest,
    identity: GatewayIdentity = Depends(
        require_user_identity
    ),
) -> dict[str, Any]:
    container = get_container()

    if request.context is not None:
        raw_context = request.context.to_context()
    else:
        raw_context = AgentContext()

    if (
        not raw_context.conversation_id
        and request.conversation_id
    ):
        raw_context.conversation_id = (
            request.conversation_id
        )

    context = container.context_resolver.resolve(
        raw_context,
        identity,
    )

    container.context_resolver.require_employee(
        context
    )

    if not context.conversation_id:
        context.conversation_id = (
            _fallback_conversation_id(
                context,
                identity,
            )
        )

    context = _apply_pilot_hr_override(
        context
    )

    session = context.session

    logger.info(
        (
            "CHAT_TRACE_START employee_id=%s "
            "conversation_id=%s message_length=%s "
            "has_token=%s has_username_hash=%s "
            "has_password_hash=%s has_digit_code=%s"
        ),
        context.employee_id,
        context.conversation_id,
        len(request.message or ""),
        bool(session and session.authorization_token),
        bool(session and session.username_hash),
        bool(session and session.password_hash),
        bool(session and session.digit_code),
    )

    try:
        data = await container.agent_orchestrator.handle(
            context,
            request.message,
        )
    except IntegrationError as exc:
        details = getattr(
            exc,
            "details",
            None,
        ) or {}

        downstream_path = str(
            details.get(
                "path",
                "",
            )
        )

        downstream_status = details.get(
            "downstreamStatusCode"
        )

        if (
            downstream_path.endswith(
                "/PostTimeEventSet"
            )
            and downstream_status == 400
        ):
            # HR_BUSINESS_MESSAGE_FUTURE_ATTENDANCE
            logger.warning(
                (
                    "HR_BUSINESS_MESSAGE_FUTURE_ATTENDANCE "
                    "employee_id=%s conversation_id=%s"
                ),
                context.employee_id,
                context.conversation_id,
            )

            data = {
                "reply": (
                    "ثبت تردد انجام نشد. "
                    "امکان ثبت تردد برای روزهای آینده وجود ندارد. "
                    "لطفاً تاریخ امروز یا یکی از روزهای گذشته را وارد کنید."
                ),
                "requiresConfirmation": False,
                "pendingAction": None,
                "data": None,
            }
        else:
            logger.exception(
                (
                    "CHAT_TRACE_FAILURE employee_id=%s "
                    "conversation_id=%s exception_type=%s "
                    "code=%s status_code=%s details=%r"
                ),
                context.employee_id,
                context.conversation_id,
                type(exc).__name__,
                getattr(
                    exc,
                    "code",
                    None,
                ),
                getattr(
                    exc,
                    "status_code",
                    None,
                ),
                details,
            )
            raise
    except Exception as exc:
        logger.exception(
            (
                "CHAT_TRACE_FAILURE employee_id=%s "
                "conversation_id=%s exception_type=%s "
                "code=%s status_code=%s details=%r"
            ),
            context.employee_id,
            context.conversation_id,
            type(exc).__name__,
            getattr(exc, "code", None),
            getattr(exc, "status_code", None),
            getattr(exc, "details", None),
        )
        raise

    logger.info(
        (
            "CHAT_TRACE_SUCCESS employee_id=%s "
            "conversation_id=%s keys=%s "
            "requires_confirmation=%s "
            "pending_action_present=%s"
        ),
        context.employee_id,
        context.conversation_id,
        sorted(data.keys()) if isinstance(data, dict) else [],
        (
            data.get("requiresConfirmation")
            if isinstance(data, dict)
            else None
        ),
        (
            bool(data.get("pendingAction"))
            if isinstance(data, dict)
            else False
        ),
    )

    # Compatibility shim for the current .NET AgentData contract.
    if (
        isinstance(data, dict)
        and data.get("data") is not None
    ):
        data = dict(data)
        data["data"] = None

    return ok(
        data,
        "پاسخ Agent آماده شد.",
    )


@router.post(
    "/action/confirm",
    response_model=ApiResponse[dict[str, Any]],
)
async def confirm_action(
    request: ConfirmActionRequest,
    identity: GatewayIdentity = Depends(
        require_user_identity
    ),
) -> dict[str, Any]:
    container = get_container()

    context = container.context_resolver.resolve(
        request.to_context(
            session=request.session,
        ),
        identity,
    )

    container.context_resolver.require_employee(
        context
    )

    data = await container.action_service.confirm(
        context,
        request.action_id,
    )

    return ok(
        data,
        "عملیات تأیید و اجرا شد.",
    )


@router.post(
    "/action/status",
    response_model=ApiResponse[dict[str, Any]],
)
async def action_status(
    request: ActionStatusRequest,
    identity: GatewayIdentity = Depends(
        require_user_identity
    ),
) -> dict[str, Any]:
    container = get_container()

    context = container.context_resolver.resolve(
        request.to_context(),
        identity,
    )

    container.context_resolver.require_employee(
        context
    )

    data = await container.action_service.status(
        context,
        request.action_id,
    )

    return ok(
        data,
        "وضعیت عملیات دریافت شد.",
    )


@router.post(
    "/action/cancel",
    response_model=ApiResponse[dict[str, Any]],
)
async def cancel_action(
    request: CancelActionRequest,
    identity: GatewayIdentity = Depends(
        require_user_identity
    ),
) -> dict[str, Any]:
    container = get_container()

    context = container.context_resolver.resolve(
        request.to_context(),
        identity,
    )

    container.context_resolver.require_employee(
        context
    )

    data = await container.action_service.cancel(
        context,
        request.action_id,
    )

    return ok(
        data,
        "عملیات لغو شد.",
    )