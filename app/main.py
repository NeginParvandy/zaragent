from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import (
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.routes.agent import router as agent_router
from app.api.routes.integration import router as integration_router
from app.api.routes.pages import router as pages_router
from app.application.container import get_container
from app.core.config import BASE_DIR, get_settings
from app.core.exceptions import (
    AppError,
    app_error_handler,
    http_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from app.core.logging import configure_logging
from app.core.middleware import (
    ForwardedHttpsMiddleware,
    RateLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)

SWAGGER_PATH = "/swagger"
SWAGGER_OAUTH_REDIRECT_PATH = "/swagger/oauth2-redirect"


def create_app() -> FastAPI:
    settings = get_settings()
    settings.validate_runtime()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        container = get_container()
        await container.start()
        try:
            yield
        finally:
            await container.close()

    docs_enabled = settings.enable_docs
    openapi_url = "/openapi.json" if docs_enabled else None

    app = FastAPI(
        title="Holding Smart Agent API",
        version=settings.app_version,
        description="Smart employee assistant with real HR and Food integrations.",
        debug=settings.app_debug,
        docs_url=None,
        redoc_url=None,
        openapi_url=openapi_url,
        swagger_ui_oauth2_redirect_url=SWAGGER_OAUTH_REDIRECT_PATH,
        lifespan=lifespan,
    )
    app.openapi_version = "3.0.3"
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    allowed_hosts = settings.allowed_host_list()
    if allowed_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(ForwardedHttpsMiddleware, enabled=settings.force_https)
    app.add_middleware(
        RateLimitMiddleware,
        requests=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
        identity_header=settings.trusted_gateway_header if settings.auth_required else "",
    )
    app.add_middleware(RequestContextMiddleware, settings=settings)

    origins = settings.cors_origin_list()
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=settings.cors_allow_credentials,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "X-Agent-Key",
                "X-Admin-Key",
                "X-Employee-Id",
                "X-Agent-Scope",
                "X-Request-Id",
            ],
            expose_headers=["X-Request-Id"],
            max_age=600,
        )

    app.mount(
        "/static",
        StaticFiles(directory=str(BASE_DIR / "app" / "static")),
        name="static",
    )

    if docs_enabled:

        @app.get(SWAGGER_PATH, include_in_schema=False)
        @app.get(f"{SWAGGER_PATH}/", include_in_schema=False)
        async def swagger_ui():
            return get_swagger_ui_html(
                openapi_url=app.openapi_url or "/openapi.json",
                title=f"{app.title} - Swagger UI",
                oauth2_redirect_url=SWAGGER_OAUTH_REDIRECT_PATH,
                swagger_js_url="/static/swagger/swagger-ui-bundle.js",
                swagger_css_url="/static/swagger/swagger-ui.css",
                swagger_favicon_url="/static/swagger/favicon-32x32.png",
                swagger_ui_parameters={"validatorUrl": None},
            )

        @app.get(SWAGGER_OAUTH_REDIRECT_PATH, include_in_schema=False)
        async def swagger_oauth_redirect():
            return get_swagger_ui_oauth2_redirect_html()

        @app.get("/docs", include_in_schema=False)
        @app.get("/docs/", include_in_schema=False)
        @app.get("/redoc", include_in_schema=False)
        @app.get("/redoc/", include_in_schema=False)
        async def legacy_docs_redirect():
            return RedirectResponse(url=SWAGGER_PATH, status_code=307)

    app.include_router(pages_router)
    app.include_router(agent_router)
    app.include_router(integration_router)
    return app


app = create_app()
