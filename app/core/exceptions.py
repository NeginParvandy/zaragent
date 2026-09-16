from __future__ import annotations

import logging
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(self, message: str, *, status_code: int = 400, code: str = "APP_ERROR", details: Any = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details


class IntegrationError(AppError):
    def __init__(self, message: str, *, status_code: int = 502, code: str = "INTEGRATION_ERROR", details: Any = None):
        super().__init__(message, status_code=status_code, code=code, details=details)


class MissingConfigurationError(AppError):
    def __init__(self, message: str, *, details: Any = None):
        super().__init__(message, status_code=400, code="MISSING_CONFIGURATION", details=details)


class NotFoundError(AppError):
    def __init__(self, message: str, *, details: Any = None):
        super().__init__(message, status_code=404, code="NOT_FOUND", details=details)


class ConflictError(AppError):
    def __init__(self, message: str, *, details: Any = None):
        super().__init__(message, status_code=409, code="CONFLICT", details=details)


def error_payload(message: str, code: str, details: Any = None) -> dict[str, Any]:
    return {"hasError": True, "data": None, "message": message, "error": {"code": code, "details": details}}


async def app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, AppError):
        raise exc
    return JSONResponse(status_code=exc.status_code, content=error_payload(exc.message, exc.code, exc.details))


async def validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    details = [
        {"field": ".".join(str(part) for part in item.get("loc", [])[1:]), "message": item.get("msg"), "type": item.get("type")}
        for item in exc.errors()
    ]
    return JSONResponse(status_code=422, content=error_payload("اطلاعات ورودی معتبر نیست.", "VALIDATION_ERROR", details))


async def http_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):
        raise exc
    message = "مسیر درخواستی پیدا نشد." if exc.status_code == 404 else str(exc.detail)
    code = "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
    return JSONResponse(status_code=exc.status_code, content=error_payload(message, code))


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled application error path=%s method=%s", request.url.path, request.method)
    return JSONResponse(
        status_code=500,
        content=error_payload("خطای داخلی کنترل‌شده رخ داد. شناسه درخواست را به تیم پشتیبانی اعلام کنید.", "UNHANDLED_ERROR"),
    )
