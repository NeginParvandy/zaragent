# -*- coding: utf-8 -*-

from __future__ import annotations

import asyncio
import copy
import py_compile
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(r"D:\serviceAi")

FOOD = (
    ROOT
    / "app"
    / "application"
    / "services"
    / "food_service.py"
)

CHAT = (
    ROOT
    / "app"
    / "application"
    / "services"
    / "chat_service.py"
)

FOOD_BACKUP = FOOD.with_name(
    "food_service.py.bak_before_food_final_part3"
)

CHAT_BACKUP = CHAT.with_name(
    "chat_service.py.bak_before_food_final_part3"
)

FOOD_MARKER = "# FOOD_FINAL_PART3_VALID_RECOMMENDATION_V1"
CHAT_MARKER = "# FOOD_FINAL_PART3_SAFE_MENU_LABEL_V1"


def require_once(
    content: str,
    needle: str,
    label: str,
) -> None:
    count = content.count(needle)

    if count != 1:
        raise RuntimeError(
            f"{label}: expected 1 occurrence, found {count}"
        )


if not FOOD.exists():
    raise FileNotFoundError(FOOD)

if not CHAT.exists():
    raise FileNotFoundError(CHAT)


original_food = FOOD.read_text(
    encoding="utf-8-sig"
)

original_chat = CHAT.read_text(
    encoding="utf-8-sig"
)

food_text = original_food
chat_text = original_chat


try:
    if not FOOD_BACKUP.exists():
        shutil.copy2(
            FOOD,
            FOOD_BACKUP,
        )

    if not CHAT_BACKUP.exists():
        shutil.copy2(
            CHAT,
            CHAT_BACKUP,
        )

    # -------------------------------------------------
    # 1. Public favorite requires a real positive signal.
    # -------------------------------------------------

    if FOOD_MARKER not in food_text:
        old_public_condition = """                if (
                    public_reservation
                    is not None
                    or average_rate
                    is not None
                ):
                    public_items.append(
"""

        require_once(
            food_text,
            old_public_condition,
            "public favorite condition",
        )

        new_public_condition = f"""                {FOOD_MARKER}
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
"""

        food_text = food_text.replace(
            old_public_condition,
            new_public_condition,
            1,
        )

        # ---------------------------------------------
        # 2. Personal recommendation must have actual
        #    positive personal history.
        # ---------------------------------------------

        personal_start_anchor = (
            "        personal_recommendation = None\n"
        )

        public_start_anchor = (
            "        public_recommendation = None\n"
        )

        require_once(
            food_text,
            personal_start_anchor,
            "personal recommendation start",
        )

        require_once(
            food_text,
            public_start_anchor,
            "public recommendation start",
        )

        personal_start = food_text.find(
            personal_start_anchor
        )

        personal_end = food_text.find(
            public_start_anchor,
            personal_start,
        )

        if (
            personal_start < 0
            or personal_end < 0
            or personal_end <= personal_start
        ):
            raise RuntimeError(
                "personal recommendation block not found"
            )

        new_personal_block = """        personal_recommendation = None

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

"""

        food_text = (
            food_text[:personal_start]
            + new_personal_block
            + food_text[personal_end:]
        )

    # -------------------------------------------------
    # 3. Defensive display rule:
    #    stale/incorrect flags cannot label 0% as
    #    a personal recommendation.
    # -------------------------------------------------

    if CHAT_MARKER not in chat_text:
        old_display_condition = """                if food.get(
                    "isRecommended"
                ):
                    details.append(
                        "⭐ پیشنهاد برای شما"
                    )
"""

        require_once(
            chat_text,
            old_display_condition,
            "menu recommendation display",
        )

        new_display_condition = f"""                {CHAT_MARKER}
                if (
                    food.get(
                        "isRecommended"
                    )
                    and (
                        parse_int(
                            interest
                        )
                        or 0
                    ) > 0
                ):
                    details.append(
                        "⭐ پیشنهاد برای شما"
                    )
"""

        chat_text = chat_text.replace(
            old_display_condition,
            new_display_condition,
            1,
        )

    FOOD.write_text(
        food_text,
        encoding="utf-8",
    )

    CHAT.write_text(
        chat_text,
        encoding="utf-8",
    )

    # -------------------------------------------------
    # 4. Syntax tests.
    # -------------------------------------------------

    py_compile.compile(
        str(FOOD),
        doraise=True,
    )

    py_compile.compile(
        str(CHAT),
        doraise=True,
    )

    # -------------------------------------------------
    # 5. Import patched classes.
    # -------------------------------------------------

    sys.path.insert(
        0,
        str(ROOT),
    )

    from app.application.services.chat_service import (
        ChatService,
    )

    from app.application.services.food_service import (
        FoodService,
    )

    # -------------------------------------------------
    # 6. Menu reply defensive tests.
    # -------------------------------------------------

    zero_interest_days = [
        {
            "date": "1405/05/05",
            "dayOfWeek": "دوشنبه",
            "selectedPlanDetailId": None,
            "foods": [
                {
                    "planDetailId": 101,
                    "foodName": "پلو یونانی",
                    "remainCount": 20,
                    "personalInterestPercent": 0,
                    "publicReservationPercent": 0,
                    "averageRate": 0,
                    "voteCount": 0,
                    "isRecommended": True,
                    "isPublicFavorite": True,
                },
            ],
        },
    ]

    zero_reply = ChatService._menu_reply(
        zero_interest_days
    )

    forbidden_zero_labels = [
        "⭐ پیشنهاد برای شما",
        "⭐ پیشنهاد شخصی هفته",
        "🔥 محبوب‌ترین انتخاب عمومی",
        "🔥 محبوب‌ترین غذای قابل رزرو",
        "رزرو عمومی:",
        "امتیاز عمومی:",
    ]

    for label in forbidden_zero_labels:
        if label in zero_reply:
            raise RuntimeError(
                "Zero-data label was displayed: "
                f"{label!r}"
            )

    positive_days = [
        {
            "date": "1405/05/05",
            "dayOfWeek": "دوشنبه",
            "selectedPlanDetailId": None,
            "foods": [
                {
                    "planDetailId": 201,
                    "foodName": "پلو یونانی",
                    "remainCount": 20,
                    "personalInterestPercent": 60,
                    "publicReservationPercent": 35,
                    "averageRate": 4.2,
                    "voteCount": 3,
                    "isRecommended": True,
                    "isPublicFavorite": True,
                },
            ],
        },
    ]

    positive_reply = ChatService._menu_reply(
        positive_days
    )

    required_positive_labels = [
        "⭐ پیشنهاد برای شما",
        "⭐ پیشنهاد شخصی هفته",
        "رزرو عمومی: 35٪ از ظرفیت",
        "امتیاز عمومی: 4.2 از ۵",
        "🔥 محبوب‌ترین انتخاب عمومی",
        "🔥 محبوب‌ترین غذای قابل رزرو",
    ]

    for label in required_positive_labels:
        if label not in positive_reply:
            raise RuntimeError(
                "Positive-data label missing: "
                f"{label!r}"
            )

    # -------------------------------------------------
    # 7. Run real get_weekly_menu_insights tests with
    #    fake API data.
    # -------------------------------------------------

    async def run_food_service_tests() -> None:
        service = object.__new__(
            FoodService
        )

        service.settings = SimpleNamespace(
            max_rating_lookups=0,
        )

        public_only_menu = {
            "restaurantId": 1,
            "mealId": 1,
            "days": [
                {
                    "date": "1405/05/05",
                    "dayOfWeek": "دوشنبه",
                    "selectedPlanDetailId": None,
                    "foods": [
                        {
                            "planDetailId": 301,
                            "foodName": "پلو یونانی",
                            "count": 100,
                            "remainCount": 30,
                            "rate": 0,
                        },
                        {
                            "planDetailId": 302,
                            "foodName": "پاستا",
                            "count": 100,
                            "remainCount": 90,
                            "rate": 0,
                        },
                    ],
                },
            ],
        }

        async def public_menu(
            context,
        ):
            return copy.deepcopy(
                public_only_menu
            )

        async def unrelated_history(
            context,
        ):
            return [
                {
                    "foodName": "غذای قدیمی",
                }
            ]

        service.get_weekly_menu = (
            public_menu
        )

        service._safe_history = (
            unrelated_history
        )

        public_result = (
            await service
            .get_weekly_menu_insights(
                None,
            )
        )

        if (
            public_result.get(
                "personalRecommendation"
            )
            is not None
        ):
            raise RuntimeError(
                "Public score created a false "
                "personal recommendation"
            )

        public_foods = (
            public_result[
                "days"
            ][0]["foods"]
        )

        if any(
            food.get("isRecommended")
            for food in public_foods
        ):
            raise RuntimeError(
                "A zero-interest food was marked "
                "as personally recommended"
            )

        if (
            public_result.get(
                "publicRecommendation"
            )
            is None
        ):
            raise RuntimeError(
                "Valid public reservation signal "
                "was not preserved"
            )

        zero_public_menu = {
            "restaurantId": 1,
            "mealId": 1,
            "days": [
                {
                    "date": "1405/05/06",
                    "dayOfWeek": "سه شنبه",
                    "selectedPlanDetailId": None,
                    "foods": [
                        {
                            "planDetailId": 401,
                            "foodName": "واویشکا",
                            "count": 100,
                            "remainCount": 100,
                            "rate": 0,
                            "ratingSummary": {
                                "averageRate": 0,
                                "voteCount": 0,
                            },
                        },
                    ],
                },
            ],
        }

        async def zero_menu(
            context,
        ):
            return copy.deepcopy(
                zero_public_menu
            )

        async def empty_history(
            context,
        ):
            return []

        service.get_weekly_menu = (
            zero_menu
        )

        service._safe_history = (
            empty_history
        )

        zero_public_result = (
            await service
            .get_weekly_menu_insights(
                None,
            )
        )

        if (
            zero_public_result.get(
                "publicRecommendation"
            )
            is not None
        ):
            raise RuntimeError(
                "Zero public data created a "
                "public favorite"
            )

        zero_public_food = (
            zero_public_result[
                "days"
            ][0]["foods"][0]
        )

        if zero_public_food.get(
            "isPublicFavorite"
        ):
            raise RuntimeError(
                "Zero public data marked a food "
                "as public favorite"
            )

        personal_menu = {
            "restaurantId": 1,
            "mealId": 1,
            "days": [
                {
                    "date": "1405/05/07",
                    "dayOfWeek": "چهارشنبه",
                    "selectedPlanDetailId": None,
                    "foods": [
                        {
                            "planDetailId": 501,
                            "foodName": "پلو یونانی",
                            "count": 100,
                            "remainCount": 80,
                            "rate": 0,
                        },
                        {
                            "planDetailId": 502,
                            "foodName": "پاستا",
                            "count": 100,
                            "remainCount": 20,
                            "rate": 0,
                        },
                    ],
                },
            ],
        }

        async def personal_menu_loader(
            context,
        ):
            return copy.deepcopy(
                personal_menu
            )

        async def personal_history(
            context,
        ):
            return [
                {
                    "foodName": "پلو یونانی",
                },
                {
                    "foodName": "پلو یونانی",
                },
            ]

        service.get_weekly_menu = (
            personal_menu_loader
        )

        service._safe_history = (
            personal_history
        )

        personal_result = (
            await service
            .get_weekly_menu_insights(
                None,
            )
        )

        recommendation = (
            personal_result.get(
                "personalRecommendation"
            )
            or {}
        )

        if (
            recommendation.get(
                "foodName"
            )
            != "پلو یونانی"
        ):
            raise RuntimeError(
                "Positive personal history did not "
                "select the correct food"
            )

        personal_foods = (
            personal_result[
                "days"
            ][0]["foods"]
        )

        recommended_names = [
            food.get("foodName")
            for food in personal_foods
            if food.get(
                "isRecommended"
            )
        ]

        if recommended_names != [
            "پلو یونانی"
        ]:
            raise RuntimeError(
                "Unexpected personal recommendation "
                f"flags: {recommended_names!r}"
            )

    asyncio.run(
        run_food_service_tests()
    )

    # -------------------------------------------------
    # 8. Verify old unsafe rules are gone.
    # -------------------------------------------------

    if (
        "        if scored_items:\n"
        in food_text
    ):
        raise RuntimeError(
            "Old unfiltered personal selection "
            "still exists"
        )

    if (
        old_public_condition
        in food_text
    ):
        raise RuntimeError(
            "Old public favorite condition "
            "still exists"
        )

    print("PATCH_OK")
    print("PART3_TESTS_OK")
    print(f"FOOD_BACKUP={FOOD_BACKUP}")
    print(f"CHAT_BACKUP={CHAT_BACKUP}")

except Exception:
    FOOD.write_text(
        original_food,
        encoding="utf-8",
    )

    CHAT.write_text(
        original_chat,
        encoding="utf-8",
    )

    print("PATCH_FAILED_ROLLED_BACK")
    raise