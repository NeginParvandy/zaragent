from __future__ import annotations

import asyncio
import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.domain.models import AgentContext
from app.domain.text import parse_float, parse_int
from app.infrastructure.clients.food_client import FoodClient


logger = logging.getLogger(__name__)

# WEEKLY_FOOD_INSPECTION_PHASE1
WEEKLY_FOOD_INSPECTION_FILE = Path(
    r"D:\serviceAi\food_weekly_inspection.json"
)


def _is_sensitive_inspection_key(key: object) -> bool:
    normalized = "".join(
        character
        for character in str(key).lower()
        if character.isalnum()
    )

    sensitive_parts = (
        "authorization",
        "token",
        "password",
        "usernamehash",
        "passwordhash",
        "digitcode",
        "session",
        "secret",
        "cookie",
        "apikey",
    )

    return any(
        part in normalized
        for part in sensitive_parts
    )


def _sanitize_inspection_value(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}

        for key, item in value.items():
            if _is_sensitive_inspection_key(key):
                continue

            sanitized[str(key)] = (
                _sanitize_inspection_value(item)
            )

        return sanitized

    if isinstance(value, list):
        return [
            _sanitize_inspection_value(item)
            for item in value
        ]

    if isinstance(value, tuple):
        return [
            _sanitize_inspection_value(item)
            for item in value
        ]

    return value


def _mask_employee_id(
    employee_id: str | None,
) -> str:
    value = str(employee_id or "").strip()

    if not value:
        return ""

    if len(value) <= 4:
        return "*" * len(value)

    return (
        "*" * (len(value) - 4)
        + value[-4:]
    )


def _unwrap(payload: Any) -> Any:
    current = payload
    for _ in range(3):
        if isinstance(current, dict) and "data" in current and len(current) <= 6:
            current = current.get("data")
            continue
        break
    return current


def _as_list(payload: Any, *keys: str) -> list[Any]:
    value = _unwrap(payload)
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in keys:
            candidate = value.get(key)
            if isinstance(candidate, list):
                return candidate
    return []


def _detail_id(detail: dict[str, Any]) -> int | str | None:
    return detail.get("id") or detail.get("planDetailId") or detail.get("planDetailID")


class FoodService:
    def __init__(self, client: FoodClient, settings: Settings):
        self.client = client
        self.settings = settings

    async def get_my_restaurants(
        self,
        context: AgentContext,
    ) -> list[dict[str, Any]]:
        """
        دریافت و یکسان‌سازی فهرست رستوران‌های مجاز کاربر جاری.

        پاسخ سرویس Food معمولاً به شکل زیر است:
        {
            "data": [
                {
                    "text": "رستوران یوتیلیتی",
                    "value": "84"
                }
            ]
        }
        """

        payload = await self.client.get_my_restaurants(
            context
        )

        rows = _as_list(
            payload,
            "items",
            "results",
            "restaurants",
        )

        restaurants: list[dict[str, Any]] = []
        seen_ids: set[int] = set()

        for item in rows:
            if not isinstance(item, dict):
                continue

            restaurant_id = parse_int(
                item.get("value")
                or item.get("restaurantId")
                or item.get("resturantId")
                or item.get("id")
            )

            if (
                restaurant_id is None
                or restaurant_id <= 0
                or restaurant_id in seen_ids
            ):
                continue

            restaurant_name = str(
                item.get("text")
                or item.get("restaurantName")
                or item.get("resturantName")
                or item.get("name")
                or ""
            ).strip()

            restaurants.append(
                {
                    "restaurantId": restaurant_id,
                    "restaurantName": (
                        restaurant_name
                        or f"رستوران {restaurant_id}"
                    ),
                }
            )

            seen_ids.add(restaurant_id)

        return restaurants

    async def get_weekly_menu(self, context: AgentContext) -> dict[str, Any]:
        payload = await self.client.get_food_plans_for_reserve(context)
        days = _as_list(payload, "items", "days", "results")
        return {
            "restaurantId": context.restaurant_id or self.settings.default_restaurant_id,
            "mealId": context.meal_id or self.settings.default_meal_id,
            "days": [self._normalize_day(day) for day in days if isinstance(day, dict)],
        }

    async def get_history(self, context: AgentContext) -> list[dict[str, Any]]:
        payload = await self.client.get_my_food_reserve(context)
        rows = _as_list(payload, "items", "results", "reserves")
        return [self._normalize_history(item) for item in rows if isinstance(item, dict)]

    async def reserve_food(self, context: AgentContext, plan_detail_id: int | str, *, idempotency_key: str | None = None) -> dict[str, Any]:
        plan_id = parse_int(plan_detail_id)
        # FOOD_NEGATIVE_IDS_V1
        if plan_id is None or plan_id == 0:
            raise AppError("شناسه غذای انتخاب‌شده معتبر نیست.", code="INVALID_PLAN_DETAIL")
        menu = await self.get_weekly_menu(context)
        target_day: dict[str, Any] | None = None
        target_food: dict[str, Any] | None = None
        for day in menu.get("days", []):
            for food in day.get("foods", []):
                if str(food.get("planDetailId")) == str(plan_id):
                    target_day, target_food = day, food
                    break
            if target_food:
                break
        if target_food is None:
            raise NotFoundError("غذای انتخاب‌شده در منوی فعلی پیدا نشد.")
        selected = target_day.get("selectedPlanDetailId") if target_day else None
        if selected:
            if str(selected) == str(plan_id):
                raise ConflictError("این غذا قبلاً برای این روز رزرو شده است.", details={"planDetailId": plan_id})
            raise ConflictError("برای این روز قبلاً غذای دیگری رزرو شده است.", details={"selectedPlanDetailId": selected})
        remain = parse_int(target_food.get("remainCount"))
        if remain is not None and remain <= 0:
            raise ConflictError("ظرفیت این غذا تمام شده است.", details={"planDetailId": plan_id})
        return await self.client.reserve_food(context, [plan_id], idempotency_key=idempotency_key)

    async def cancel_food(self, context: AgentContext, plan_detail_id: int | str, *, idempotency_key: str | None = None) -> dict[str, Any]:
        plan_id = parse_int(plan_detail_id)
        if plan_id is None or plan_id == 0:
            raise AppError("شناسه رزرو غذا معتبر نیست.", code="INVALID_PLAN_DETAIL")
        menu = await self.get_weekly_menu(context)
        selected_ids = {str(day.get("selectedPlanDetailId")) for day in menu.get("days", []) if day.get("selectedPlanDetailId")}
        if str(plan_id) not in selected_ids:
            raise ConflictError("این رزرو دیگر فعال نیست یا قبلاً حذف شده است.", details={"planDetailId": plan_id})
        return await self.client.delete_food_reserve(context, plan_id, idempotency_key=idempotency_key)

    async def get_rating(self, context: AgentContext, *, reserve_id: int | str = 0, plan_detail_id: int | str = 0) -> dict[str, Any]:
        return await self.client.get_food_rate_comment(context, reserve_id=reserve_id, plan_detail_id=plan_detail_id)

    async def set_rating(
        self,
        context: AgentContext,
        *,
        reserve_id: int | str,
        rate: int,
        comment: str,
        is_anonymous: bool,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        safe_reserve_id = parse_int(reserve_id)
        safe_rate = parse_int(rate)
        if safe_reserve_id is None or safe_reserve_id == 0:
            raise AppError("شناسه رزرو برای ثبت امتیاز معتبر نیست.", code="INVALID_RESERVE_ID")
        if safe_rate is None or safe_rate < 1 or safe_rate > 5:
            raise AppError("امتیاز باید بین ۱ تا ۵ باشد.", code="INVALID_RATING")
        return await self.client.set_food_rate_comment(
            context,
            reserve_id=safe_reserve_id,
            rate=safe_rate,
            comment=(comment or "").strip()[:1000],
            is_anonymous=is_anonymous,
            idempotency_key=idempotency_key,
        )


    async def get_weekly_menu_insights(
        self,
        context: AgentContext,
        target_date: str | None = None,
        *,
        max_days: int = 7,
    ) -> dict[str, Any]:
        # FOOD_RECOMMENDATION_V3
        menu, history = await asyncio.gather(
            self.get_weekly_menu(context),
            self._safe_history(context),
        )

        days: list[dict[str, Any]] = []

        for raw_day in (
            menu.get("days")
            or []
        ):
            if not isinstance(
                raw_day,
                dict,
            ):
                continue

            day = dict(raw_day)

            day["foods"] = [
                dict(food)
                for food in (
                    raw_day.get("foods")
                    or []
                )
                if isinstance(
                    food,
                    dict,
                )
            ]

            days.append(day)

        if target_date:
            days = [
                day
                for day in days
                if str(
                    day.get("date")
                    or ""
                )
                == str(target_date)
            ]
        elif max_days > 0:
            days = days[:max_days]

        def food_key(
            value: Any,
        ) -> str:
            return " ".join(
                str(
                    value
                    or ""
                )
                .replace(
                    "ي",
                    "ی",
                )
                .replace(
                    "ك",
                    "ک",
                )
                .strip()
                .lower()
                .split()
            )

        history_names = [
            food_key(
                item.get("foodName")
            )
            for item in history
            if isinstance(
                item,
                dict,
            )
            and food_key(
                item.get("foodName")
            )
        ]

        history_counter = Counter(
            history_names
        )

        max_history_count = (
            max(
                history_counter.values()
            )
            if history_counter
            else 0
        )

        available_foods: list[
            dict[str, Any]
        ] = []

        for day in days:
            if day.get(
                "selectedPlanDetailId"
            ):
                continue

            for food in (
                day.get("foods")
                or []
            ):
                if (
                    isinstance(
                        food,
                        dict,
                    )
                    and self._has_capacity(
                        food
                    )
                ):
                    available_foods.append(
                        food
                    )

        rating_limit = max(
            0,
            int(
                self.settings
                .max_rating_lookups
                or 0
            ),
        )

        if rating_limit:
            await self._enrich_ratings(
                context,
                available_foods[
                    :rating_limit
                ],
            )

        scored_items: list[
            tuple[
                float,
                float,
                float,
                dict[str, Any],
                dict[str, Any],
            ]
        ] = []

        public_items: list[
            tuple[
                float,
                float,
                int,
                dict[str, Any],
                dict[str, Any],
            ]
        ] = []

        for day in days:
            if day.get(
                "selectedPlanDetailId"
            ):
                continue

            for food in (
                day.get("foods")
                or []
            ):
                if not isinstance(
                    food,
                    dict,
                ):
                    continue

                if not self._has_capacity(
                    food
                ):
                    continue

                name_key = food_key(
                    food.get("foodName")
                )

                history_hits = (
                    history_counter.get(
                        name_key,
                        0,
                    )
                )

                personal_interest = (
                    round(
                        (
                            history_hits
                            / max_history_count
                        )
                        * 100
                    )
                    if max_history_count
                    else None
                )

                total_count = parse_int(
                    food.get("count")
                )

                remain_count = parse_int(
                    food.get(
                        "remainCount"
                    )
                )

                public_reservation = None

                if (
                    total_count is not None
                    and total_count > 0
                    and remain_count
                    is not None
                ):
                    reserved_count = max(
                        0,
                        min(
                            total_count,
                            (
                                total_count
                                - remain_count
                            ),
                        ),
                    )

                    public_reservation = (
                        round(
                            (
                                reserved_count
                                / total_count
                            )
                            * 100
                        )
                    )

                rating_summary = (
                    food.get(
                        "ratingSummary"
                    )
                    if isinstance(
                        food.get(
                            "ratingSummary"
                        ),
                        dict,
                    )
                    else {}
                )

                average_rate = parse_float(
                    rating_summary.get(
                        "averageRate"
                    )
                )

                if average_rate is None:
                    average_rate = (
                        parse_float(
                            food.get("rate")
                        )
                    )

                if average_rate is not None:
                    average_rate = max(
                        0.0,
                        min(
                            5.0,
                            float(
                                average_rate
                            ),
                        ),
                    )

                vote_count = (
                    parse_int(
                        rating_summary.get(
                            "voteCount"
                        )
                    )
                    or 0
                )

                rating_percent = (
                    round(
                        (
                            average_rate
                            / 5
                        )
                        * 100,
                        2,
                    )
                    if average_rate
                    is not None
                    else None
                )

                recommendation_score = (
                    (
                        personal_interest
                        or 0
                    )
                    * 0.50
                    + (
                        public_reservation
                        or 0
                    )
                    * 0.30
                    + (
                        rating_percent
                        or 0
                    )
                    * 0.20
                )

                food[
                    "personalInterestPercent"
                ] = personal_interest

                food[
                    "publicReservationPercent"
                ] = public_reservation

                food[
                    "averageRate"
                ] = (
                    round(
                        average_rate,
                        2,
                    )
                    if average_rate
                    is not None
                    else None
                )

                food[
                    "voteCount"
                ] = vote_count

                food[
                    "recommendationScore"
                ] = round(
                    recommendation_score,
                    2,
                )

                food[
                    "isRecommended"
                ] = False

                food[
                    "isPublicFavorite"
                ] = False

                scored_items.append(
                    (
                        recommendation_score,
                        float(
                            public_reservation
                            if public_reservation
                            is not None
                            else -1
                        ),
                        float(
                            average_rate
                            if average_rate
                            is not None
                            else -1
                        ),
                        food,
                        day,
                    )
                )

                # FOOD_FINAL_PART3_VALID_RECOMMENDATION_V1
                valid_public_signal = (
                    (
                        public_reservation
                        is not None
                        and float(
                            public_reservation
                        ) > 0
                    )
                    or (
                        vote_count > 0
                        and average_rate
                        is not None
                        and float(
                            average_rate
                        ) > 0
                    )
                )

                if valid_public_signal:
                    public_items.append(
                        (
                            float(
                                public_reservation
                                if public_reservation
                                is not None
                                else -1
                            ),
                            float(
                                average_rate
                                if average_rate
                                is not None
                                else -1
                            ),
                            vote_count,
                            food,
                            day,
                        )
                    )

        personal_recommendation = None

        personal_items = [
            item
            for item in scored_items
            if float(
                item[3].get(
                    "personalInterestPercent"
                )
                or 0
            ) > 0
        ]

        if personal_items:
            best_item = max(
                personal_items,
                key=lambda item: (
                    item[0],
                    item[1],
                    item[2],
                ),
            )

            best_food = best_item[3]
            best_day = best_item[4]

            best_food[
                "isRecommended"
            ] = True

            personal_recommendation = {
                "foodName": (
                    best_food.get(
                        "foodName"
                    )
                ),
                "date": (
                    best_day.get("date")
                ),
                "dayOfWeek": (
                    best_day.get(
                        "dayOfWeek"
                    )
                ),
                "score": round(
                    best_item[0],
                    2,
                ),
                "personalInterestPercent": (
                    best_food.get(
                        "personalInterestPercent"
                    )
                ),
            }

        public_recommendation = None

        if public_items:
            public_best = max(
                public_items,
                key=lambda item: (
                    item[0],
                    item[1],
                    item[2],
                ),
            )

            public_food = public_best[3]
            public_day = public_best[4]

            public_food[
                "isPublicFavorite"
            ] = True

            public_recommendation = {
                "foodName": (
                    public_food.get(
                        "foodName"
                    )
                ),
                "date": (
                    public_day.get("date")
                ),
                "dayOfWeek": (
                    public_day.get(
                        "dayOfWeek"
                    )
                ),
                "publicReservationPercent": (
                    public_food.get(
                        "publicReservationPercent"
                    )
                ),
                "averageRate": (
                    public_food.get(
                        "averageRate"
                    )
                ),
                "voteCount": (
                    public_food.get(
                        "voteCount"
                    )
                ),
            }

        return {
            "restaurantId": (
                menu.get(
                    "restaurantId"
                )
            ),
            "mealId": (
                menu.get("mealId")
            ),
            "days": days,
            "historyCount": len(
                history
            ),
            "personalRecommendation": (
                personal_recommendation
            ),
            "publicRecommendation": (
                public_recommendation
            ),
        }


    async def recommend_food(self, context: AgentContext, target_date: str | None = None) -> dict[str, Any]:
        menu, history = await asyncio.gather(
            self.get_weekly_menu(context),
            self._safe_history(context),
        )

        await self._write_weekly_inspection(
            context=context,
            menu=menu,
            history=history,
        )

        favorite_names = self._favorite_food_names(history)
        target_days = menu["days"]
        if target_date:
            target_days = [day for day in target_days if day.get("date") == target_date]
        already_reserved = [
            {"date": day.get("date"), "selectedPlanDetailId": day.get("selectedPlanDetailId")}
            for day in target_days
            if day.get("selectedPlanDetailId")
        ]
        candidate_days = [day for day in target_days if not day.get("selectedPlanDetailId")]
        candidates = [food for day in candidate_days for food in day.get("foods", []) if self._has_capacity(food)]
        await self._enrich_ratings(context, candidates[: self.settings.max_rating_lookups])

        recommendations: list[dict[str, Any]] = []
        for day in candidate_days:
            available_foods = [food for food in day.get("foods", []) if self._has_capacity(food)]
            best = self._best_food_candidate(available_foods, favorite_names)
            if best:
                recommendations.append(
                    {
                        "date": day.get("date"),
                        "dayOfWeek": day.get("dayOfWeek"),
                        "food": best,
                        "message": self._recommendation_message(day, best, favorite_names),
                    }
                )
        return {"recommendations": recommendations, "alreadyReserved": already_reserved, "menu": menu}

    async def _enrich_ratings(self, context: AgentContext, foods: list[dict[str, Any]]) -> None:
        semaphore = asyncio.Semaphore(self.settings.rating_lookup_concurrency)

        async def enrich(item: dict[str, Any]) -> None:
            plan_detail_id = item.get("planDetailId")
            if not plan_detail_id:
                return
            try:
                async with semaphore:
                    rating = await self.get_rating(context, reserve_id=0, plan_detail_id=plan_detail_id)
                data = _unwrap(rating)
                item["ratingSummary"] = self._rating_summary(data if isinstance(data, dict) else {})
            except Exception as exc:
                logger.warning("Food rating lookup failed plan_detail_id=%s error=%s", plan_detail_id, type(exc).__name__)

        await asyncio.gather(*(enrich(food) for food in foods))

    async def _safe_history(self, context: AgentContext) -> list[dict[str, Any]]:
        try:
            return await self.get_history(context)
        except Exception as exc:
            logger.warning("Food history lookup failed error=%s", type(exc).__name__)
            return []


    async def _write_weekly_inspection(
        self,
        *,
        context: AgentContext,
        menu: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> None:
        try:
            inspection_payload = {
                "employeeIdMasked": _mask_employee_id(
                    context.employee_id
                ),
                "restaurantId": context.restaurant_id,
                "mealId": context.meal_id,
                "menu": menu,
                "history": history,
            }

            sanitized_payload = (
                _sanitize_inspection_value(
                    inspection_payload
                )
            )

            output_text = json.dumps(
                sanitized_payload,
                ensure_ascii=False,
                indent=2,
                default=str,
            )

            await asyncio.to_thread(
                WEEKLY_FOOD_INSPECTION_FILE.write_text,
                output_text,
                encoding="utf-8",
            )

            logger.info(
                "Weekly food inspection saved path=%s",
                WEEKLY_FOOD_INSPECTION_FILE,
            )

        except Exception as exc:
            logger.warning(
                "Weekly food inspection failed "
                "error=%s",
                type(exc).__name__,
            )

    def _normalize_day(self, day: dict[str, Any]) -> dict[str, Any]:
        details = day.get("details") or day.get("foods") or day.get("items") or []
        foods = []
        for detail in details if isinstance(details, list) else []:
            if not isinstance(detail, dict):
                continue
            foods.append(
                {
                    "planDetailId": _detail_id(detail),
                    "planId": detail.get("planId") or day.get("id") or day.get("planId"),
                    "foodName": detail.get("foodName") or detail.get("name") or detail.get("title") or "",
                    "description": detail.get("description") or detail.get("foodDescription") or "",
                    "sideDishesName": detail.get("sideDishesName") or "",
                    "imageName": detail.get("imageName") or detail.get("foodImageName"),
                    "count": parse_int(detail.get("count")),
                    "remainCount": parse_int(detail.get("remainCount")),
                    "rate": parse_float(detail.get("rate")),
                }
            )
        return {
            "planId": day.get("id") or day.get("planId"),
            "date": day.get("date") or day.get("jalaliDate") or "",
            "miladyDate": day.get("miladyDate"),
            "dayOfWeek": day.get("dayOfWeek") or day.get("dayName") or "",
            "selectedPlanDetailId": day.get("selectedPlanDetailId") or day.get("selectedPlanDetailID"),
            "foods": foods,
        }

    @staticmethod
    def _normalize_history(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "reserveId": item.get("reserveId") or item.get("id"),
            "planDetailId": item.get("planDetailId"),
            "foodName": item.get("foodName") or item.get("name") or "",
            "date": item.get("date") or item.get("reserveDate"),
        }

    @staticmethod
    def _favorite_food_names(history: list[dict[str, Any]]) -> list[str]:
        counter: Counter[str] = Counter()
        for item in history:
            name = str(item.get("foodName") or "").strip()
            if name:
                counter[name] += 1
        return [name for name, _ in counter.most_common(5)]

    @staticmethod
    def _rating_summary(data: dict[str, Any]) -> dict[str, Any]:
        rating_list = data.get("ratingList") or []
        total_count = 0
        weighted = 0
        for row in rating_list if isinstance(rating_list, list) else []:
            if not isinstance(row, dict):
                continue
            stars = parse_int(row.get("id"))
            count = parse_int(row.get("title"), 0)
            if stars is None or count is None:
                continue
            total_count += count
            weighted += stars * count
        fallback_rate = parse_float(data.get("rate"))
        average = round(weighted / total_count, 2) if total_count else fallback_rate
        comments = data.get("commentsList") or []
        return {"averageRate": average, "voteCount": total_count, "commentsCount": len(comments) if isinstance(comments, list) else 0}

    @staticmethod
    def _has_capacity(food: dict[str, Any]) -> bool:
        remain = parse_int(food.get("remainCount"))
        return remain is None or remain > 0

    def _best_food_candidate(self, foods: list[dict[str, Any]], favorite_names: list[str]) -> dict[str, Any] | None:
        if not foods:
            return None
        favorite_set = {name.strip() for name in favorite_names}
        scored: list[tuple[float, dict[str, Any]]] = []
        for item in foods:
            rating = item.get("ratingSummary") or {}
            average = parse_float(rating.get("averageRate") or item.get("rate"))
            vote_count = parse_int(rating.get("voteCount"), 0) or 0
            remain = parse_int(item.get("remainCount"))
            favorite_bonus = 1.5 if item.get("foodName") in favorite_set else 0
            capacity_bonus = 0.3 if remain is None or remain > self.settings.low_capacity_threshold else 0
            score = average + favorite_bonus + min(vote_count, 20) * 0.02 + capacity_bonus
            scored.append((score, item))
        return max(scored, key=lambda pair: pair[0])[1]

    def _recommendation_message(self, day: dict[str, Any], food: dict[str, Any], favorite_names: list[str]) -> str:
        name = food.get("foodName") or "این غذا"
        target_date = day.get("date") or "این روز"
        rating = food.get("ratingSummary") or {}
        average = parse_float(rating.get("averageRate") or food.get("rate"))
        vote_count = parse_int(rating.get("voteCount"), 0) or 0
        remain = parse_int(food.get("remainCount"))
        parts = [f"برای {target_date}، «{name}» {'که قبلاً انتخابش کرده‌ای ' if name in set(favorite_names) else ''}گزینه پیشنهادی است."]
        if average:
            parts.append(f"امتیاز آن {average:g} از ۵" + (f" بر اساس {vote_count} رأی" if vote_count else "") + " است.")
        if remain is not None and remain <= self.settings.low_capacity_threshold:
            parts.append(f"فقط {remain} ظرفیت باقی مانده است.")
        parts.append("در صورت تأیید، رزرو واقعی انجام می‌شود.")
        return " ".join(parts)
