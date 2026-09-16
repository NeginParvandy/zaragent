from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, RedirectResponse, Response

from app.core.config import Settings
from app.core.exceptions import error_payload
from app.core.logging import request_id_var


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings):
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-Id") or uuid4().hex
        token = request_id_var.set(request_id)
        try:
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    declared_length = int(content_length)
                except ValueError:
                    return JSONResponse(
                        status_code=400,
                        content=error_payload("هدر Content-Length معتبر نیست.", "INVALID_CONTENT_LENGTH"),
                        headers={"X-Request-Id": request_id},
                    )
                if declared_length < 0 or declared_length > self.settings.max_request_body_bytes:
                    return JSONResponse(
                        status_code=413,
                        content=error_payload("حجم درخواست بیش از حد مجاز است.", "REQUEST_TOO_LARGE"),
                        headers={"X-Request-Id": request_id},
                    )

            if request.method in {"POST", "PUT", "PATCH"}:
                body = await request.body()
                if len(body) > self.settings.max_request_body_bytes:
                    return JSONResponse(
                        status_code=413,
                        content=error_payload("حجم درخواست بیش از حد مجاز است.", "REQUEST_TOO_LARGE"),
                        headers={"X-Request-Id": request_id},
                    )

            response = await call_next(request)
            response.headers["X-Request-Id"] = request_id
            return response
        finally:
            request_id_var.reset(token)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply strict headers while allowing locally hosted Swagger assets."""

    @staticmethod
    def _is_docs_path(path: str) -> bool:
        return path in {
            "/swagger",
            "/swagger/",
            "/swagger/oauth2-redirect",
            "/docs",
            "/docs/",
            "/redoc",
            "/redoc/",
            "/openapi.json",
        } or path.startswith(("/swagger/", "/docs/", "/redoc/"))

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        if self._is_docs_path(request.url.path):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "base-uri 'self'; "
                "object-src 'none'; "
                "frame-ancestors 'none'; "
                "form-action 'self'; "
                "script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: blob:; "
                "font-src 'self' data:; "
                "connect-src 'self';"
            )
        else:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "base-uri 'self'; "
                "object-src 'none'; "
                "frame-ancestors 'none'; "
                "form-action 'self'; "
                "script-src 'self'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; "
                "font-src 'self' data:; "
                "connect-src 'self';"
            )

        response.headers["Cache-Control"] = "no-store"
        return response


class ForwardedHttpsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, enabled: bool):
        super().__init__(app)
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next) -> Response:
        forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme).lower()
        if self.enabled and forwarded_proto != "https":
            url = request.url.replace(scheme="https")
            return RedirectResponse(str(url), status_code=307)
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    EXCLUDED_PATHS = {
        "/",
        "/swagger",
        "/swagger/",
        "/swagger/oauth2-redirect",
        "/docs",
        "/docs/",
        "/redoc",
        "/redoc/",
        "/openapi.json",
        "/favicon.ico",
        "/api/agent/live",
        "/api/agent/ready",
    }

    def __init__(self, app, requests: int, window_seconds: int, identity_header: str):
        super().__init__(app)
        self.limit = max(1, requests)
        self.window = max(1, window_seconds)
        self.identity_header = identity_header
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()
        self._request_count = 0

    async def dispatch(self, request: Request, call_next) -> Response:
        if self._is_excluded_path(request.url.path):
            return await call_next(request)

        trusted_identity = request.headers.get(self.identity_header) if self.identity_header else None
        key = trusted_identity or (request.client.host if request.client else "unknown")
        now = time.monotonic()

        async with self._lock:
            self._request_count += 1
            if self._request_count % 500 == 0:
                stale_before = now - self.window
                stale_keys = [
                    item_key
                    for item_key, item_bucket in self._hits.items()
                    if not item_bucket or item_bucket[-1] <= stale_before
                ]
                for item_key in stale_keys:
                    self._hits.pop(item_key, None)

            bucket = self._hits[key]
            while bucket and bucket[0] <= now - self.window:
                bucket.popleft()

            if len(bucket) >= self.limit:
                retry_after = max(1, int(self.window - (now - bucket[0])))
                return JSONResponse(
                    status_code=429,
                    content=error_payload(
                        "تعداد درخواست‌ها بیش از حد مجاز است.",
                        "RATE_LIMITED",
                        {"retryAfterSeconds": retry_after},
                    ),
                    headers={"Retry-After": str(retry_after)},
                )
            bucket.append(now)

        return await call_next(request)

    @classmethod
    def _is_excluded_path(cls, path: str) -> bool:
        return path in cls.EXCLUDED_PATHS or path.startswith(
            ("/static/", "/swagger/", "/docs/", "/redoc/")
        )
