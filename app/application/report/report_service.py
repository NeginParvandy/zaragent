from __future__ import annotations


class ReportService:

    def __init__(
        self,
        attendance_service,
        leave_service,
    ):
        self.attendance_service = attendance_service
        self.leave_service = leave_service