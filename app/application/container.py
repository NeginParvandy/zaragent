from __future__ import annotations

import asyncio
import logging
from functools import lru_cache

from app.application.attendance.attendance_service import AttendanceService
from app.application.attendance.attendance_handler import AttendanceHandler

from app.application.leave.leave_handler import LeaveHandler
from app.application.leave.leave_service import LeaveService

from app.application.mission.mission_service import MissionService
from app.application.mission.mission_handler import MissionHandler

from app.application.report.report_service import ReportService
from app.application.report.report_handler import ReportHandler

from app.application.handlers.monthly_attendance_handler import (
    MonthlyAttendanceHandler,
)
from app.application.orchestration.agent_orchestrator import AgentOrchestrator
from app.application.services.action_service import ActionService
from app.application.services.chat_service import ChatService
from app.application.services.context_resolver import ContextResolver
from app.application.services.daily_brief_service import DailyBriefService
from app.application.services.food_service import FoodService
from app.application.services.hr_service import HrService
from app.application.services.reminder_service import ReminderService
from app.application.services.snapshot_service import SnapshotService
from app.core.config import get_settings
from app.infrastructure.clients.food_client import FoodClient
from app.infrastructure.clients.personnel_client import PersonnelClient
from app.infrastructure.repositories.state_repository import StateRepository


logger = logging.getLogger(__name__)


class Container:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.repository = StateRepository(
            self.settings
        )
        self.context_resolver = ContextResolver(
            self.settings
        )
        self.food_client = FoodClient(
            self.settings
        )
        self.personnel_client = PersonnelClient(
            self.settings
        )
        self.food_service = FoodService(
            self.food_client,
            self.settings,
        )
        self.hr_service = HrService(
            self.personnel_client
        )
        self.attendance_service = AttendanceService(
            self.hr_service
        )
        self.leave_service = LeaveService(
            self.hr_service
        )
        self.report_service = ReportService(
            self.attendance_service,
            self.leave_service,
        )
        self.mission_service = MissionService(
            self.hr_service
        )
        self.attendance_service = AttendanceService(
            self.hr_service
        )
        self.action_service = ActionService(
            self.settings,
            self.repository,
            self.food_service,
            self.hr_service,
        )
        self.leave_handler = LeaveHandler(
            self.leave_service,
            self.action_service,
        )
        self.mission_handler = MissionHandler(
            self.mission_service,
            self.action_service,
        )
        self.attendance_handler = AttendanceHandler(
            self.attendance_service,
            self.action_service,
        )
        self.snapshot_service = SnapshotService(
            self.settings,
            self.food_service,
            self.hr_service,
        )
        self.reminder_service = ReminderService(
            self.settings,
            self.repository,
            self.snapshot_service,
            self.action_service,
        )
        self.daily_brief_service = DailyBriefService(
            self.snapshot_service,
            self.reminder_service,
        )
        self.chat_service = ChatService(
            self.food_service,
            self.hr_service,
            self.action_service,
            self.daily_brief_service,
            self.repository,
            self.attendance_handler,
            self.leave_handler,
            self.mission_handler,
            self.report_handler,
        )
        self.monthly_attendance_handler = MonthlyAttendanceHandler()
        self.agent_orchestrator = AgentOrchestrator(
            handlers=(
                self.monthly_attendance_handler,
            ),
            fallback=self.chat_service,
        )
        self._maintenance_task: (
            asyncio.Task[None] | None
        ) = None

    async def start(self) -> None:
        await asyncio.gather(
            self.food_client.start(),
            self.personnel_client.start(),
        )
        cleanup_result = await asyncio.to_thread(
            self.repository.cleanup
        )
        logger.info(
            "Initial state cleanup completed: %s",
            cleanup_result,
        )
        self._maintenance_task = (
            asyncio.create_task(
                self._maintenance_loop(),
                name="agent-state-maintenance",
            )
        )

    async def close(self) -> None:
        if self._maintenance_task is not None:
            self._maintenance_task.cancel()
            try:
                await self._maintenance_task
            except asyncio.CancelledError:
                pass
            self._maintenance_task = None

        await asyncio.gather(
            self.food_client.close(),
            self.personnel_client.close(),
        )

    async def _maintenance_loop(
        self,
    ) -> None:
        interval_seconds = (
            self.settings
            .maintenance_interval_minutes
            * 60
        )

        while True:
            await asyncio.sleep(
                interval_seconds
            )
            try:
                cleanup_result = (
                    await asyncio.to_thread(
                        self.repository.cleanup
                    )
                )
                logger.info(
                    "Periodic state cleanup completed: %s",
                    cleanup_result,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Periodic state cleanup failed"
                )


@lru_cache(maxsize=1)
def get_container() -> Container:
    return Container()