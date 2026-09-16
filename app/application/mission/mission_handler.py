from __future__ import annotations

from typing import Any


class MissionHandler:

    def __init__(
        self,
        mission_service,
        action_service,
    ):
        self.mission_service = mission_service
        self.action_service = action_service


    def can_create(
        self,
        text: str,
    ) -> bool:

        from .mission_rules import (
            is_mission_create,
        )

        return is_mission_create(text)

    async def create_mission(
            self,
            context,
            text: str,
            dates: list[str],
            times: list[str],
    ) -> dict[str, Any]:
        return {
            "reply": (
                "درخواست ماموریت دریافت شد، "
                "اما سرویس ماموریت هنوز فعال نشده است."
            ),
            "requiresConfirmation": False,
        }


    def can_delete(
        self,
        text: str,
    ) -> bool:

        from .mission_rules import (
            is_mission_delete,
        )

        return is_mission_delete(text)


    async def delete_mission(
            self,
            context,
            text: str,
            dates: list[str],
    ) -> dict[str, Any]:
        return {
            "reply": (
                "درخواست ماموریت دریافت شد، "
                "اما سرویس ماموریت هنوز فعال نشده است."
            ),
            "requiresConfirmation": False,
        }

    def can_list(
        self,
        text: str,
    ) -> bool:

        from .mission_rules import (
            is_mission_list,
        )

        return is_mission_list(text)