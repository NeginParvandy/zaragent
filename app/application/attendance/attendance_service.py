from __future__ import annotations


class AttendanceService:

    def __init__(
        self,
        hr_service,
    ) -> None:
        self.hr = hr_service


    async def get_time_events(
        self,
        context,
        start_date: str,
        end_date: str,
    ) -> dict:

        return await self.hr.get_time_events(
            context,
            start_date,
            end_date,
        )


    async def get_daily_attendance(
        self,
        context,
        date: str,
    ) -> dict:

        result = await self.get_time_events(
            context,
            date,
            date,
        )

        rows = result.get("data") or []

        return {
            "date": date,
            "events": (
                rows
                if isinstance(rows, list)
                else []
            ),
            "count": (
                len(rows)
                if isinstance(rows, list)
                else 0
            ),
        }


    async def get_period_attendance(
        self,
        context,
        start_date: str,
        end_date: str,
    ) -> dict:

        result = await self.get_time_events(
            context,
            start_date,
            end_date,
        )

        rows = result.get("data") or []

        return {
            "startDate": start_date,
            "endDate": end_date,
            "events": (
                rows
                if isinstance(rows, list)
                else []
            ),
        }


    def validate_time_event_distance(
        self,
        rows,
        time,
    ):
        return self.hr.validate_time_event_distance(
            rows,
            time,
        )