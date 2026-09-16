from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.domain.models import AgentContext
from app.infrastructure.clients.base_client import ExternalApiClient


class FoodClient(ExternalApiClient):
    def __init__(
        self,
        settings: Settings,
    ):
        super().__init__(
            settings,
            base_url=settings.food_api_base_url,
            service_name="Food",
        )

    async def get_my_restaurants(
        self,
        context: AgentContext,
    ) -> dict[str, Any]:
        """
        دریافت رستوران‌های مجاز کاربر جاری.

        کاربر توسط Authorization Token موجود در
        context.session شناسایی می‌شود.
        """

        return await self.request(
            "GET",
            "/api/v{version}/ResturantUsers/get-My-resturant",
            context=context,
        )

    async def get_food_plans_for_reserve(
        self,
        context: AgentContext,
    ) -> dict[str, Any]:
        restaurant_id = (
            context.restaurant_id
            or self.settings.default_restaurant_id
        )

        meal_id = (
            context.meal_id
            or self.settings.default_meal_id
        )

        params = {
            "resturantId": restaurant_id,
            "mealId": meal_id,
        }

        return await self.request(
            "GET",
            "/api/v{version}/FoodPlans/get-FoodPlansForReserve",
            context=context,
            params=params,
        )

    async def get_my_food_reserve(
        self,
        context: AgentContext,
    ) -> dict[str, Any]:
        return await self.request(
            "GET",
            "/api/v{version}/FoodReserves/get-MyFoodReserve",
            context=context,
        )

    async def reserve_food(
        self,
        context: AgentContext,
        plan_detail_ids: list[int],
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        return await self.request(
            "POST",
            "/api/v{version}/FoodReserves/Food-Reserve",
            context=context,
            json=plan_detail_ids,
            idempotency_key=idempotency_key,
        )

    async def delete_food_reserve(
        self,
        context: AgentContext,
        plan_detail_id: int | str,
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        return await self.request(
            "POST",
            "/api/v{version}/FoodReserves/delete-FoodReserve",
            context=context,
            json={
                "planDetailId": str(plan_detail_id),
            },
            idempotency_key=idempotency_key,
        )

    async def get_food_rate_comment(
        self,
        context: AgentContext,
        *,
        reserve_id: int | str = 0,
        plan_detail_id: int | str = 0,
    ) -> dict[str, Any]:
        params = {
            "reserveId": reserve_id,
            "planDetailId": plan_detail_id,
        }

        return await self.request(
            "GET",
            "/api/v{version}/FoodReserves/Get_Food_Rate&Comment",
            context=context,
            params=params,
        )

    async def set_food_rate_comment(
        self,
        context: AgentContext,
        *,
        reserve_id: int | str,
        rate: int,
        comment: str,
        is_anonymous: bool,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        body = {
            "id": str(reserve_id),
            "rate": int(rate),
            "comment": comment or "",
            "isAnonymous": bool(is_anonymous),
        }

        return await self.request(
            "POST",
            "/api/v{version}/FoodReserves/Set_Food_Rate&Comment",
            context=context,
            json=body,
            idempotency_key=idempotency_key,
        )