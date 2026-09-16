from __future__ import annotations


class LeaveService:

    def __init__(
        self,
        hr_service,
    ):
        self.hr = hr_service


    async def get_leave_balance(
            self,
            context,
            date: str,
    ):
        return await self.get_time_account(
            context,
            date,
        )


    async def get_leave_types(
        self,
        context,
    ):
        return await self.hr.get_leave_types(
            context,
        )


    def find_leave_type(
        self,
        rows,
        text: str,
    ):
        return self.hr.find_leave_type(
            rows,
            text,
        )


    async def get_leave_requests(
        self,
        context,
        date: str,
    ):
        return await self.hr.get_leave_requests(
            context,
            date,
        )