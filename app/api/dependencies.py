from __future__ import annotations

from dataclasses import dataclass

from fastapi import Header, Request

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.security import secure_equals


@dataclass(frozen=True)
class GatewayIdentity:
    employee_id: str | None
    scope: str
    authenticated: bool
    authorization_token: str | None = None


async def require_user_identity(
    request: Request,
    x_agent_key: str | None = Header(
        default=None,
        alias="X-Agent-Key",
    ),
    x_agent_scope: str | None = Header(
        default="user",
        alias="X-Agent-Scope",
    ),
) -> GatewayIdentity:
    settings = get_settings()

    authorization_token = str(
        request.headers.get("Authorization")
        or ""
    ).strip() or None

    # Compatibility mode:
    # The existing application contract is accepted as-is.
    # When the caller forwards the user's Authorization header,
    # it is preserved in GatewayIdentity so ContextResolver can
    # pass it to downstream Food and HR services.
    if not settings.auth_required:
        return GatewayIdentity(
            employee_id=None,
            scope=x_agent_scope or "user",
            authenticated=False,
            authorization_token=authorization_token,
        )

    x_employee_id = request.headers.get(
        settings.trusted_gateway_header
    )

    if not secure_equals(
        x_agent_key,
        settings.agent_api_key,
    ):
        raise AppError(
            "احراز هویت Gateway نامعتبر است.",
            status_code=401,
            code="UNAUTHORIZED",
        )

    if not x_employee_id:
        raise AppError(
            "هویت کاربر از Gateway ارسال نشده است.",
            status_code=401,
            code="MISSING_IDENTITY",
        )

    return GatewayIdentity(
        employee_id=x_employee_id.strip(),
        scope=x_agent_scope or "user",
        authenticated=True,
        authorization_token=authorization_token,
    )


async def require_admin_identity(
    x_admin_key: str | None = Header(
        default=None,
        alias="X-Admin-Key",
    ),
) -> GatewayIdentity:
    settings = get_settings()

    if not settings.enable_admin_endpoints:
        raise AppError(
            "مسیر مدیریتی فعال نیست.",
            status_code=404,
            code="NOT_FOUND",
        )

    if not secure_equals(
        x_admin_key,
        settings.admin_api_key,
    ):
        raise AppError(
            "دسترسی مدیریتی نامعتبر است.",
            status_code=403,
            code="FORBIDDEN",
        )

    return GatewayIdentity(
        employee_id=None,
        scope="admin",
        authenticated=True,
        authorization_token=None,
    )