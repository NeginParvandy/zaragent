from __future__ import annotations

from typing import Any

from app.application.services.monthly_attendance_chat_demo import (
    handle_monthly_attendance_demo,
)
from app.application.services.nlu_core import normalize_text as normalize_nlu_text
from app.domain.models import AgentContext
from app.domain.text import normalize_persian_text


class MonthlyAttendanceHandler:
    """Owns monthly-attendance chat requests during the migration period.

    The existing monthly-attendance implementation is intentionally reused so
    this extraction changes responsibility boundaries without changing the
    current user-visible behavior.
    """

    async def try_handle(
        self,
        context: AgentContext,
        message: str,
    ) -> dict[str, Any] | None:
        text = normalize_nlu_text(
            normalize_persian_text(message)
        )
        return await handle_monthly_attendance_demo(
            context,
            text,
        )
