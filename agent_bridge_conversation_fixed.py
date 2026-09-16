from __future__ import annotations

import asyncio
import hashlib
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

    data = await container.chat_service.handle(
        context,
        request.message,
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