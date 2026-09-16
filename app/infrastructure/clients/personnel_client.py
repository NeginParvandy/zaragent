from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.core.config import Settings
from app.core.exceptions import MissingConfigurationError
from app.core.security import secret_value
from app.domain.models import AgentContext
from app.infrastructure.clients.base_client import ExternalApiClient


class PersonnelClient(ExternalApiClient):
    def __init__(self, settings: Settings):
        super().__init__(settings, base_url=settings.hr_api_base_url, service_name="HR")

    def _hr_credentials(self, context: AgentContext | None) -> tuple[str, str, int]:
        session = self._session(context)
        username = secret_value(session.username_hash) or self.settings.default_username_hash.get_secret_value()
        password = secret_value(session.password_hash) or self.settings.default_password_hash.get_secret_value()
        digit = session.digit_code if session.digit_code is not None else self.settings.default_digit_code
        missing: list[str] = []
        if not username:
            missing.append("usernameHash")
        if not password:
            missing.append("passwordHash")
        if digit is None:
            missing.append("digitCode")
        if missing or digit is None:
            raise MissingConfigurationError("اطلاعات احراز هویت HR کامل نیست.", details={"missing": missing})
        return username, password, int(digit)

    def _query_auth(self, context: AgentContext) -> dict[str, Any]:
        username, password, digit = self._hr_credentials(context)
        return {"UsernameHash": username, "PasswordHash": password, "digitCode": digit}

    def _json_auth(self, context: AgentContext) -> dict[str, Any]:
        username, password, digit = self._hr_credentials(context)
        return {"usernameHash": username, "passwordHash": password, "digitCode": digit}

    def _form_auth(self, context: AgentContext) -> dict[str, Any]:
        username, password, digit = self._hr_credentials(context)
        return {"UsernameHash": username, "PasswordHash": password, "DigitCode": digit}

    async def get(self, route: str, context: AgentContext, params: dict[str, Any] | None = None) -> dict[str, Any]:
        final_params = {**(params or {}), **self._query_auth(context)}
        return await self.request("GET", f"/api/v{{version}}/Personnel/{route}", context=context, params=final_params)

    async def post_json(
        self, route: str, context: AgentContext, payload: dict[str, Any], *, idempotency_key: str | None = None
    ) -> dict[str, Any]:
        body = {**payload, **self._json_auth(context)}
        return await self.request(
            "POST",
            f"/api/v{{version}}/Personnel/{route}",
            context=context,
            json=body,
            headers={"Content-Type": "application/json"},
            idempotency_key=idempotency_key,
        )

    async def post_form(
        self,
        route: str,
        context: AgentContext,
        data: dict[str, Any],
        files: Iterable[tuple[str, tuple[str, bytes, str]]] | None = None,
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        body = {**data, **self._form_auth(context)}
        return await self.request(
            "POST",
            f"/api/v{{version}}/Personnel/{route}",
            context=context,
            data=body,
            files=list(files or []),
            idempotency_key=idempotency_key,
        )
