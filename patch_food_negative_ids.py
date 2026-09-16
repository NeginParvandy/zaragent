# -*- coding: utf-8 -*-

from __future__ import annotations

import asyncio
import py_compile
import shutil
import sys
from pathlib import Path


ROOT = Path(r"D:\serviceAi")

FOOD = (
    ROOT
    / "app"
    / "application"
    / "services"
    / "food_service.py"
)

BACKUP = FOOD.with_name(
    "food_service.py.bak_before_negative_food_ids"
)

MARKER = "# FOOD_NEGATIVE_IDS_V1"


def require_count(
    content: str,
    needle: str,
    expected: int,
    label: str,
) -> None:
    actual = content.count(needle)

    if actual != expected:
        raise RuntimeError(
            f"{label}: expected {expected}, found {actual}"
        )


if not FOOD.exists():
    raise FileNotFoundError(FOOD)


original_text = FOOD.read_text(
    encoding="utf-8-sig"
)

text = original_text


if MARKER in text:
    print("ALREADY_PATCHED")
    raise SystemExit(0)


try:
    if not BACKUP.exists():
        shutil.copy2(
            FOOD,
            BACKUP,
        )

    plan_condition = (
        "if plan_id is None or plan_id <= 0:"
    )

    reserve_condition = (
        "if safe_reserve_id is None "
        "or safe_reserve_id <= 0:"
    )

    require_count(
        text,
        plan_condition,
        2,
        "planDetailId validation",
    )

    require_count(
        text,
        reserve_condition,
        1,
        "reserveId validation",
    )

    text = text.replace(
        plan_condition,
        (
            f"{MARKER}\n"
            "        if plan_id is None "
            "or plan_id == 0:"
        ),
        1,
    )

    text = text.replace(
        plan_condition,
        (
            "if plan_id is None "
            "or plan_id == 0:"
        ),
        1,
    )

    text = text.replace(
        reserve_condition,
        (
            "if safe_reserve_id is None "
            "or safe_reserve_id == 0:"
        ),
        1,
    )

    FOOD.write_text(
        text,
        encoding="utf-8",
    )

    py_compile.compile(
        str(FOOD),
        doraise=True,
    )

    sys.path.insert(
        0,
        str(ROOT),
    )

    from app.application.services.food_service import (
        FoodService,
    )

    from app.core.exceptions import AppError

    class FakeClient:
        def __init__(self) -> None:
            self.reserved_ids = None
            self.deleted_id = None
            self.rated_id = None

        async def reserve_food(
            self,
            context,
            plan_detail_ids,
            *,
            idempotency_key=None,
        ):
            self.reserved_ids = list(
                plan_detail_ids
            )

            return {
                "ok": True,
                "planDetailIds": (
                    self.reserved_ids
                ),
            }

        async def delete_food_reserve(
            self,
            context,
            plan_detail_id,
            *,
            idempotency_key=None,
        ):
            self.deleted_id = (
                plan_detail_id
            )

            return {
                "ok": True,
                "planDetailId": (
                    plan_detail_id
                ),
            }

        async def set_food_rate_comment(
            self,
            context,
            *,
            reserve_id,
            rate,
            comment,
            is_anonymous,
            idempotency_key=None,
        ):
            self.rated_id = reserve_id

            return {
                "ok": True,
                "reserveId": reserve_id,
            }

    async def run_tests() -> None:
        service = object.__new__(
            FoodService
        )

        service.client = FakeClient()

        negative_plan_id = (
            -2147483225
        )

        negative_reserve_id = (
            -9223372036854774910
        )

        async def menu_loader(
            context,
        ):
            return {
                "restaurantId": 84,
                "mealId": 1,
                "days": [
                    {
                        "date": "1405/05/04",
                        "dayOfWeek": "یکشنبه",
                        "selectedPlanDetailId": None,
                        "foods": [
                            {
                                "planDetailId": (
                                    negative_plan_id
                                ),
                                "foodName": (
                                    "قیمه سیب زمینی"
                                ),
                                "remainCount": 10,
                            },
                        ],
                    },
                ],
            }

        service.get_weekly_menu = (
            menu_loader
        )

        await service.reserve_food(
            None,
            negative_plan_id,
        )

        if service.client.reserved_ids != [
            negative_plan_id
        ]:
            raise RuntimeError(
                "Negative planDetailId "
                "was not forwarded correctly"
            )

        async def reserved_menu_loader(
            context,
        ):
            return {
                "restaurantId": 84,
                "mealId": 1,
                "days": [
                    {
                        "date": "1405/05/04",
                        "dayOfWeek": "یکشنبه",
                        "selectedPlanDetailId": (
                            negative_plan_id
                        ),
                        "foods": [
                            {
                                "planDetailId": (
                                    negative_plan_id
                                ),
                                "foodName": (
                                    "قیمه سیب زمینی"
                                ),
                                "remainCount": 10,
                            },
                        ],
                    },
                ],
            }

        service.get_weekly_menu = (
            reserved_menu_loader
        )

        await service.cancel_food(
            None,
            negative_plan_id,
        )

        if (
            service.client.deleted_id
            != negative_plan_id
        ):
            raise RuntimeError(
                "Negative cancellation ID "
                "was not forwarded correctly"
            )

        await service.set_rating(
            None,
            reserve_id=(
                negative_reserve_id
            ),
            rate=4,
            comment="تست",
            is_anonymous=False,
        )

        if (
            service.client.rated_id
            != negative_reserve_id
        ):
            raise RuntimeError(
                "Negative reserveId was not "
                "forwarded correctly"
            )

        invalid_calls = [
            (
                "reserve zero",
                lambda: service.reserve_food(
                    None,
                    0,
                ),
            ),
            (
                "cancel zero",
                lambda: service.cancel_food(
                    None,
                    0,
                ),
            ),
            (
                "rating zero",
                lambda: service.set_rating(
                    None,
                    reserve_id=0,
                    rate=4,
                    comment="تست",
                    is_anonymous=False,
                ),
            ),
        ]

        for label, call in invalid_calls:
            try:
                await call()
            except AppError:
                pass
            else:
                raise RuntimeError(
                    f"{label} was incorrectly accepted"
                )

    asyncio.run(
        run_tests()
    )

    if (
        "plan_id is None or plan_id <= 0"
        in text
    ):
        raise RuntimeError(
            "Old planDetailId validation remains"
        )

    if (
        "safe_reserve_id is None "
        "or safe_reserve_id <= 0"
        in text
    ):
        raise RuntimeError(
            "Old reserveId validation remains"
        )

    print("PATCH_OK")
    print("NEGATIVE_ID_TESTS_OK")
    print(f"BACKUP={BACKUP}")

except Exception:
    FOOD.write_text(
        original_text,
        encoding="utf-8",
    )

    print("PATCH_FAILED_ROLLED_BACK")
    raise