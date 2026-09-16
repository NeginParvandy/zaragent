from __future__ import annotations

from typing import Any


class ReportHandler:

    def __init__(
        self,
        report_service,
    ):
        self.report_service = report_service


    def can_handle(
        self,
        text: str,
    ) -> bool:

        from .report_rules import (
            is_report_request,
        )

        return is_report_request(text)


    async def handle(
        self,
        context,
    ) -> dict[str, Any]:

        return {
            "reply": (
                "گزارش عملکرد آماده انتقال منطق است."
            ),
            "requiresConfirmation": False,
        }