from __future__ import annotations

from pydantic import SecretStr

from app.api.dependencies import GatewayIdentity
from app.core.config import Settings
from app.core.exceptions import (
    AppError,
    MissingConfigurationError,
)
from app.core.time import local_jalali_today
from app.domain.models import (
    AgentContext,
    UserSession,
)


class ContextResolver:
    def __init__(
        self,
        settings: Settings,
    ):
        self.settings = settings

    def resolve(
        self,
        context: AgentContext | None,
        identity: GatewayIdentity | None = None,
    ) -> AgentContext:
        ctx = (
            context or AgentContext()
        ).model_copy(deep=True)

        session = ctx.session or UserSession()

        gateway_authorization = str(
            getattr(
                identity,
                "authorization_token",
                None,
            )
            or ""
        ).strip()

        # A token explicitly supplied in context.session has
        # priority. Otherwise, preserve the Authorization
        # header forwarded by the application or Gateway.
        if (
            session.authorization_token is None
            and gateway_authorization
        ):
            session = session.model_copy(
                update={
                    "authorization_token": SecretStr(
                        gateway_authorization
                    ),
                }
            )

        trusted_employee = (
            identity.employee_id
            if identity
            else None
        )

        if trusted_employee:
            if (
                ctx.employee_id
                and str(ctx.employee_id)
                != str(trusted_employee)
            ):
                raise AppError(
                    (
                        "کد پرسنلی Body با هویت معتبر "
                        "Gateway تطابق ندارد."
                    ),
                    status_code=403,
                    code="IDENTITY_MISMATCH",
                )

            ctx.employee_id = trusted_employee

        elif (
            not ctx.employee_id
            and not self.settings.auth_required
            and self.settings.default_employee_id
        ):
            ctx.employee_id = (
                self.settings.default_employee_id
            )

        if not ctx.date:
            ctx.date = local_jalali_today(
                self.settings.app_timezone
            )

        if (
            ctx.restaurant_id is None
            and self.settings.default_restaurant_id
            is not None
        ):
            ctx.restaurant_id = (
                self.settings.default_restaurant_id
            )

        if (
            ctx.meal_id is None
            and self.settings.default_meal_id
            is not None
        ):
            ctx.meal_id = (
                self.settings.default_meal_id
            )

        ctx.session = session
        return ctx

    def require_employee(
        self,
        context: AgentContext,
    ) -> str:
        employee = context.employee_id

        if not employee:
            raise MissingConfigurationError(
                "کد پرسنلی کاربر مشخص نیست.",
                details={
                    "field": "employeeId",
                },
            )

        return str(employee)
