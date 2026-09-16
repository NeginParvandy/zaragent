from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.api.dependencies import GatewayIdentity, require_admin_identity
from app.application.container import get_container
from app.core.response import ok
from app.domain.models import ApiResponse

router = APIRouter(prefix="/api/integration", tags=["Integration"])


@router.get("/config", response_model=ApiResponse[dict[str, Any]])
async def config(_: GatewayIdentity = Depends(require_admin_identity)) -> dict[str, Any]:
    container = get_container()
    return ok(container.settings.config_status(), "وضعیت امن تنظیمات دریافت شد.")
