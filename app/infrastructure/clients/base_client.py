from __future__ import annotations

import asyncio
import logging
import secrets
import time
from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import IntegrationError, MissingConfigurationError
from app.core.security import normalize_bearer_token, sanitize_text, secret_value
from app.domain.models import AgentContext, UserSession

logger = logging.getLogger(__name__)


class ExternalApiClient:
    def __init__(self, settings: Settings, *, base_url: str, service_name: str):
        self.settings = settings
        self.base_url = base_url.rstrip("/")
        self.service_name = service_name
        self._client: httpx.AsyncClient | None = None
        self._client_lock = asyncio.Lock()
        self._failure_count = 0
        self._circuit_opened_at: float | None = None

    def _path(self, path: str) -> str:
        path = path.format(version=self.settings.api_version).lstrip("/")
        return f"{self.base_url}/{path}"

    def _session(self, context: AgentContext | None) -> UserSession:
        return context.session if context and context.session else UserSession()

    def _employee_id(self, context: AgentContext | None) -> str:
        employee_id = (context.employee_id if context else None) or self.settings.default_employee_id
        if not employee_id:
            raise MissingConfigurationError("کد پرسنلی کاربر به Agent ارسال نشده است.", details={"field": "employeeId"})
        return str(employee_id)

    def _auth_token(self, context: AgentContext | None) -> str:
        session = self._session(context)
        return secret_value(session.authorization_token) or self.settings.default_auth_token.get_secret_value()

    def _auth_headers(self, context: AgentContext | None) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        token = self._auth_token(context)
        if token:
            headers["Authorization"] = normalize_bearer_token(token)
        return headers

    def _secrets(self, context: AgentContext | None) -> list[object]:
        session = self._session(context)
        return [
            session.authorization_token,
            session.username_hash,
            session.password_hash,
            session.digit_code,
            self.settings.default_auth_token,
            self.settings.default_username_hash,
            self.settings.default_password_hash,
            self.settings.default_digit_code,
        ]

    async def start(self) -> None:
        await self._get_client()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        async with self._client_lock:
            if self._client is None:
                timeout = httpx.Timeout(
                    timeout=self.settings.request_timeout_seconds,
                    connect=self.settings.connect_timeout_seconds,
                )
                limits = httpx.Limits(max_connections=50, max_keepalive_connections=20, keepalive_expiry=30)
                self._client = httpx.AsyncClient(
                    timeout=timeout,
                    verify=self.settings.ssl_verify_value(),
                    limits=limits,
                    follow_redirects=False,
                    headers={"User-Agent": f"HoldingSmartAgent/{self.settings.app_version}"},
                )
        return self._client

    def _assert_circuit_available(self) -> None:
        if self._circuit_opened_at is None:
            return
        if time.monotonic() - self._circuit_opened_at >= self.settings.circuit_reset_seconds:
            self._failure_count = 0
            self._circuit_opened_at = None
            return
        raise IntegrationError(
            f"ارتباط با سرویس {self.service_name} موقتاً متوقف شده است.",
            status_code=503,
            code="DOWNSTREAM_CIRCUIT_OPEN",
            details={"service": self.service_name},
        )

    def _record_success(self) -> None:
        self._failure_count = 0
        self._circuit_opened_at = None

    def _record_failure(self) -> None:
        self._failure_count += 1
        if self._failure_count >= self.settings.circuit_failure_threshold:
            self._circuit_opened_at = time.monotonic()

    async def request(
        self,
        method: str,
        path: str,
        *,
        context: AgentContext | None = None,
        params: dict[str, Any] | None = None,
        json: Any = None,
        data: dict[str, Any] | None = None,
        files: Any = None,
        headers: dict[str, str] | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        self._assert_circuit_available()
        client = await self._get_client()
        url = self._path(path)
        final_headers = {**self._auth_headers(context), **(headers or {})}
        if idempotency_key:
            final_headers["Idempotency-Key"] = idempotency_key

        retries = self.settings.external_get_retries if method.upper() == "GET" else 0
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=final_headers,
                    params=params,
                    json=json,
                    data=data,
                    files=files,
                )
                result = self._parse_response(response, path, context)
                self._record_success()
                return result
            except httpx.RequestError as exc:
                last_error = exc
                self._record_failure()
                if attempt >= retries:
                    break
                delay = self.settings.retry_backoff_seconds * (2**attempt) + secrets.randbelow(151) / 1000
                await asyncio.sleep(delay)
            except IntegrationError as exc:
                last_error = exc
                retryable = method.upper() == "GET" and exc.status_code in {502, 503, 504}
                if not retryable or attempt >= retries:
                    raise
                await asyncio.sleep(self.settings.retry_backoff_seconds * (2**attempt) + secrets.randbelow(151) / 1000)

        logger.warning(
            "Downstream request failed service=%s path=%s error=%s",
            self.service_name,
            path,
            type(last_error).__name__ if last_error else "unknown",
        )
        raise IntegrationError(
            f"اتصال به سرویس {self.service_name} برقرار نشد.",
            status_code=503,
            code="DOWNSTREAM_UNAVAILABLE",
            details={"service": self.service_name, "reason": sanitize_text(str(last_error), self._secrets(context))},
        ) from last_error

    def _parse_response(self, response: httpx.Response, path: str, context: AgentContext | None) -> Any:
        raw = response.text or ""
        payload: Any = None
        content_type = (response.headers.get("content-type") or "").lower()
        if raw and "json" in content_type:
            try:
                payload = response.json()
            except ValueError:
                payload = None
        elif raw and not raw.lstrip().startswith("<"):
            try:
                payload = response.json()
            except ValueError:
                payload = None

        if response.status_code >= 400:
            message = payload.get("message") or payload.get("detail") if isinstance(payload, dict) else raw
            status_code, code = self._map_downstream_status(response.status_code)
            self._record_failure()
            raise IntegrationError(
                sanitize_text(message or f"خطای سرویس {self.service_name}", self._secrets(context)),
                status_code=status_code,
                code=code,
                details={"service": self.service_name, "path": path, "downstreamStatusCode": response.status_code},
            )

        if response.status_code == 204 or not raw.strip():
            return {"statusCode": response.status_code, "success": True}
        if raw.lstrip().startswith("<"):
            raise IntegrationError(
                f"سرویس {self.service_name} پاسخ HTML/XML نامعتبر برگرداند.",
                code="DOWNSTREAM_INVALID_CONTENT",
                details={"service": self.service_name, "path": path},
            )
        if payload is None:
            raise IntegrationError(
                f"پاسخ سرویس {self.service_name} JSON معتبر نیست.",
                code="DOWNSTREAM_INVALID_JSON",
                details={"service": self.service_name, "path": path},
            )
        if isinstance(payload, dict) and payload.get("hasError") is True:
            raise IntegrationError(
                sanitize_text(payload.get("message") or f"سرویس {self.service_name} خطا برگرداند.", self._secrets(context)),
                code="DOWNSTREAM_BUSINESS_ERROR",
                details={"service": self.service_name, "path": path},
            )
        return payload

    @staticmethod
    def _map_downstream_status(status_code: int) -> tuple[int, str]:
        if status_code in {400, 422}:
            return 422, "DOWNSTREAM_VALIDATION_ERROR"
        if status_code == 401:
            return 502, "DOWNSTREAM_AUTHENTICATION_ERROR"
        if status_code == 403:
            return 502, "DOWNSTREAM_AUTHORIZATION_ERROR"
        if status_code == 404:
            return 404, "DOWNSTREAM_NOT_FOUND"
        if status_code == 409:
            return 409, "DOWNSTREAM_CONFLICT"
        if status_code == 429:
            return 503, "DOWNSTREAM_RATE_LIMITED"
        if status_code in {408, 504}:
            return 504, "DOWNSTREAM_TIMEOUT"
        return 502, "DOWNSTREAM_HTTP_ERROR"
