from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.application.services.food_service import FoodService
from app.application.services.hr_service import HrService
from app.core.config import Settings
from app.domain.models import AgentContext

logger = logging.getLogger(__name__)


class SnapshotService:
    def __init__(self, settings: Settings, food: FoodService, hr: HrService):
        self.settings = settings
        self.food = food
        self.hr = hr

    async def fetch(self, context: AgentContext, date: str) -> dict[str, Any]:
        async def safe(name: str, factory: Callable[[], Awaitable[Any]]) -> dict[str, Any]:
            try:
                value = await asyncio.wait_for(factory(), timeout=self.settings.use_case_timeout_seconds)
                return {"data": value, "error": None}
            except TimeoutError:
                logger.warning("Snapshot source timed out source=%s", name)
                return {"data": None, "error": "TIMEOUT"}
            except Exception as exc:
                logger.warning("Snapshot source failed source=%s error=%s", name, type(exc).__name__)
                return {"data": None, "error": type(exc).__name__}

        food, attendance, leave = await asyncio.gather(
            safe("food", lambda: self.food.get_weekly_menu(context)),
            safe("attendance", lambda: self.hr.get_time_events(context, date, date)),
            safe("leave", lambda: self.hr.get_leave_requests(context, date)),
        )
        return {"date": date, "food": food, "attendance": attendance, "leave": leave}
