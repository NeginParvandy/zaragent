# -*- coding: utf-8 -*-

from __future__ import annotations

import py_compile
import shutil
import sys
from pathlib import Path


ROOT = Path(r"D:\serviceAi")

CHAT = (
    ROOT
    / "app"
    / "application"
    / "services"
    / "chat_service.py"
)

BACKUP = CHAT.with_name(
    "chat_service.py.bak_before_food_final_part2"
)

MARKER = "# FOOD_FINAL_PART2_EXACT_RESERVATION_V1"


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


if not CHAT.exists():
    raise FileNotFoundError(CHAT)


original_text = CHAT.read_text(
    encoding="utf-8-sig"
)

text = original_text


if MARKER in text:
    print("ALREADY_PATCHED")
    raise SystemExit(0)


try:
    if not BACKUP.exists():
        shutil.copy2(
            CHAT,
            BACKUP,
        )

    # -------------------------------------------------
    # 1. Explicit weekday must override stale activeDate.
    # -------------------------------------------------

    old_weekday_block = """        if (
            requested_weekday
            and not target_date
        ):
            menu_cache = (
                await self.food.get_weekly_menu(
                    context
                )
            )
            target_date = (
                self._infer_menu_date_from_days(
                    text,
                    menu_cache.get("days")
                    or [],
                )
            )
"""

    require_once(
        text,
        old_weekday_block,
        "weekday resolution block",
    )

    new_weekday_block = f"""        {MARKER}
        if (
            requested_weekday
            and not has_explicit_numeric_date
            and not has_explicit_named_date
            and not has_relative_date
        ):
            menu_cache = (
                await self.food.get_weekly_menu(
                    context
                )
            )

            resolved_weekday_date = (
                self._infer_menu_date_from_days(
                    text,
                    menu_cache.get("days")
                    or [],
                )
            )

            if resolved_weekday_date:
                target_date = (
                    resolved_weekday_date
                )

        elif (
            requested_weekday
            and not target_date
        ):
            menu_cache = (
                await self.food.get_weekly_menu(
                    context
                )
            )

            target_date = (
                self._infer_menu_date_from_days(
                    text,
                    menu_cache.get("days")
                    or [],
                )
            )
"""

    text = text.replace(
        old_weekday_block,
        new_weekday_block,
        1,
    )

    # -------------------------------------------------
    # 2. Add exact food-name extraction and matching
    #    against fresh API menu days.
    # -------------------------------------------------

    helper_anchor = """    def _find_food_candidates(
"""

    require_once(
        text,
        helper_anchor,
        "food candidate helper anchor",
    )

    helper_code = r'''    @staticmethod
    def _requested_food_tokens(
        text: str,
    ) -> set[str]:
        normalized = normalize_nlu_text(
            text
        )

        tokens = set(
            re.findall(
                r"[a-zA-Z]+|[0-9]+|"
                r"[\u0600-\u06FF]+",
                normalized,
            )
        )

        stop_words = {
            "غذا",
            "غذای",
            "غذاها",
            "منو",
            "ناهار",
            "خوراک",
            "رستوران",
            "رزرو",
            "ثبت",
            "انتخاب",
            "سفارش",
            "کن",
            "کنم",
            "کنید",
            "شه",
            "شود",
            "بشه",
            "بده",
            "بگیر",
            "بگیرش",
            "برام",
            "برایم",
            "برای",
            "رو",
            "را",
            "لطفا",
            "لطفاً",
            "میخوام",
            "میخواهم",
            "می",
            "خواهم",
            "امروز",
            "فردا",
            "پس",
            "پسفردا",
            "این",
            "هفته",
            "بعد",
            "شنبه",
            "یکشنبه",
            "دوشنبه",
            "سه",
            "سهشنبه",
            "چهارشنبه",
            "چهار",
            "پنجشنبه",
            "پنج",
            "جمعه",
            "فروردین",
            "اردیبهشت",
            "خرداد",
            "تیر",
            "مرداد",
            "شهریور",
            "مهر",
            "آبان",
            "آذر",
            "دی",
            "بهمن",
            "اسفند",
        }

        return {
            token
            for token in tokens
            if token not in stop_words
            and not token.isdigit()
            and len(token) >= 2
        }

    @classmethod
    def _find_food_candidates_in_days(
        cls,
        text: str,
        days: list[Any],
        target_date: str | None = None,
    ) -> list[dict[str, Any]]:
        normalized_text = normalize_nlu_text(
            text
        )

        query_tokens = (
            cls._requested_food_tokens(
                text
            )
        )

        if not query_tokens:
            return []

        safe_target_date = str(
            target_date or ""
        ).strip()

        candidates: list[
            dict[str, Any]
        ] = []

        for day in days:
            if not isinstance(day, dict):
                continue

            day_date = str(
                day.get("date") or ""
            ).strip()

            if (
                safe_target_date
                and day_date
                != safe_target_date
            ):
                continue

            for food in day.get(
                "foods"
            ) or []:
                if not isinstance(food, dict):
                    continue

                food_name = str(
                    food.get("foodName")
                    or ""
                ).strip()

                if not food_name:
                    continue

                normalized_name = (
                    normalize_nlu_text(
                        food_name
                    )
                )

                name_tokens = set(
                    re.findall(
                        r"[a-zA-Z]+|[0-9]+|"
                        r"[\u0600-\u06FF]+",
                        normalized_name,
                    )
                )

                exact_match = bool(
                    normalized_name
                    and normalized_name
                    in normalized_text
                )

                overlap = (
                    query_tokens
                    & name_tokens
                )

                token_match = bool(
                    overlap
                    and (
                        query_tokens
                        <= name_tokens
                        or name_tokens
                        <= query_tokens
                        or len(overlap) >= 2
                    )
                )

                if not (
                    exact_match
                    or token_match
                ):
                    continue

                score = (
                    100
                    if exact_match
                    else 0
                )

                score += len(overlap) * 10

                if (
                    query_tokens
                    <= name_tokens
                ):
                    score += 5

                candidates.append(
                    {
                        "day": dict(day),
                        "food": dict(food),
                        "score": score,
                    }
                )

        candidates.sort(
            key=lambda item: (
                int(
                    item.get("score")
                    or 0
                ),
                str(
                    item.get(
                        "day",
                        {},
                    ).get("date")
                    or ""
                ),
            ),
            reverse=True,
        )

        return candidates

'''

    text = text.replace(
        helper_anchor,
        helper_code + helper_anchor,
        1,
    )

    # -------------------------------------------------
    # 3. Search the fresh menu before recommendation.
    #    Named food must never silently fall back to a
    #    different recommended food.
    # -------------------------------------------------

    old_named_block = """        named_candidates = (
            self._find_food_candidates(
                text,
                conversation_payload,
            )
        )

        if named_candidates:
            return await self._prepare_named_food_reservation(
                context,
                text,
                named_candidates,
                (
                    str(target_date)
                    if target_date
                    else None
                ),
                restaurant_data,
                conversation_payload,
            )

        recommendation = (
"""

    require_once(
        text,
        old_named_block,
        "named reservation block",
    )

    new_named_block = """        reservation_menu = (
            menu_cache
            or await self.food.get_weekly_menu(
                context
            )
        )

        reservation_days = [
            dict(day)
            for day in (
                reservation_menu.get(
                    "days"
                )
                or []
            )
            if isinstance(day, dict)
        ]

        named_candidates = (
            self._find_food_candidates_in_days(
                text,
                reservation_days,
                (
                    str(target_date)
                    if target_date
                    else None
                ),
            )
        )

        if named_candidates:
            fresh_payload = dict(
                conversation_payload
            )
            fresh_payload[
                "recentMenus"
            ] = self._merge_menu_days(
                fresh_payload.get(
                    "recentMenus"
                ),
                reservation_days,
            )

            return await self._prepare_named_food_reservation(
                context,
                text,
                named_candidates,
                (
                    str(target_date)
                    if target_date
                    else None
                ),
                restaurant_data,
                fresh_payload,
            )

        requested_food_tokens = (
            self._requested_food_tokens(
                text
            )
        )

        if requested_food_tokens:
            relevant_days = (
                self._filter_menu_days(
                    reservation_days,
                    (
                        str(target_date)
                        if target_date
                        else None
                    ),
                    text,
                )
            )

            available_names: list[str] = []

            for day in relevant_days:
                for food in (
                    day.get("foods")
                    or []
                ):
                    if not isinstance(
                        food,
                        dict,
                    ):
                        continue

                    food_name = str(
                        food.get("foodName")
                        or ""
                    ).strip()

                    remain_count = (
                        parse_int(
                            food.get(
                                "remainCount"
                            )
                        )
                    )

                    if (
                        not food_name
                        or (
                            remain_count
                            is not None
                            and remain_count <= 0
                        )
                    ):
                        continue

                    if (
                        food_name
                        not in available_names
                    ):
                        available_names.append(
                            food_name
                        )

            target_label = (
                requested_weekday
                or str(
                    target_date
                    or ""
                ).strip()
                or "بازه موردنظر"
            )

            reply = (
                "غذای نام‌برده‌شده در منوی "
                f"{target_label} پیدا نشد."
            )

            if available_names:
                reply += (
                    " گزینه‌های قابل رزرو: "
                    + "، ".join(
                        available_names[:8]
                    )
                    + "."
                )

            return {
                "reply": reply,
                "requiresConfirmation": False,
                "data": {
                    **reservation_menu,
                    "restaurant": (
                        restaurant_data
                    ),
                    "date": target_date,
                    "days": relevant_days,
                    "requestedFoodFound": (
                        False
                    ),
                },
            }

        recommendation = (
"""

    text = text.replace(
        old_named_block,
        new_named_block,
        1,
    )

    # -------------------------------------------------
    # 4. Never fall back to the same food on another
    #    day when a preferred date was specified.
    # -------------------------------------------------

    old_candidate_fallback = """        if not preferred_candidates:
            preferred_candidates = (
                candidates
            )
"""

    require_once(
        text,
        old_candidate_fallback,
        "preferred candidate fallback",
    )

    new_candidate_fallback = """        if not preferred_candidates:
            if preferred_date:
                return {
                    "reply": (
                        "غذای نام‌برده‌شده برای "
                        f"{preferred_date} پیدا نشد."
                    ),
                    "requiresConfirmation": False,
                    "data": {
                        "date": preferred_date,
                        "restaurant": restaurant,
                        "requestedFoodFound": False,
                    },
                }

            preferred_candidates = (
                candidates
            )
"""

    text = text.replace(
        old_candidate_fallback,
        new_candidate_fallback,
        1,
    )

    # -------------------------------------------------
    # 5. Synchronize the final correct food date back
    #    into conversation state.
    # -------------------------------------------------

    state_anchor = """        data = response_data

        restaurant = data.get(
"""

    require_once(
        text,
        state_anchor,
        "response state anchor",
    )

    state_replacement = """        data = response_data

        response_date = str(
            data.get("date")
            or ""
        ).strip()

        if (
            response_date
            and str(
                nlu_result.get(
                    "domain"
                )
                or ""
            )
            == "FOOD"
        ):
            saved_nlu_state = dict(
                updated_payload.get(
                    "nluState"
                )
                or {}
            )

            saved_entities = dict(
                saved_nlu_state.get(
                    "entities"
                )
                or {}
            )

            saved_entities[
                "date"
            ] = response_date

            saved_nlu_state[
                "domain"
            ] = "FOOD"

            saved_nlu_state[
                "entities"
            ] = saved_entities

            updated_payload[
                "nluState"
            ] = saved_nlu_state

            updated_payload[
                "activeDate"
            ] = response_date

        restaurant = data.get(
"""

    text = text.replace(
        state_anchor,
        state_replacement,
        1,
    )

    CHAT.write_text(
        text,
        encoding="utf-8",
    )

    # -------------------------------------------------
    # 6. Syntax test.
    # -------------------------------------------------

    py_compile.compile(
        str(CHAT),
        doraise=True,
    )

    # -------------------------------------------------
    # 7. Runtime tests for exact food matching.
    # -------------------------------------------------

    sys.path.insert(
        0,
        str(ROOT),
    )

    from app.application.services.chat_service import (
        ChatService,
    )

    service = object.__new__(
        ChatService
    )

    sample_days = [
        {
            "date": "1405/05/04",
            "dayOfWeek": "یکشنبه",
            "selectedPlanDetailId": None,
            "foods": [
                {
                    "planDetailId": 101,
                    "foodName": (
                        "قیمه سیب زمینی"
                    ),
                    "remainCount": 10,
                },
                {
                    "planDetailId": 102,
                    "foodName": "کوبیده",
                    "remainCount": 10,
                },
            ],
        },
        {
            "date": "1405/05/05",
            "dayOfWeek": "دوشنبه",
            "selectedPlanDetailId": None,
            "foods": [
                {
                    "planDetailId": 201,
                    "foodName": "پلو یونانی",
                    "remainCount": 10,
                },
            ],
        },
        {
            "date": "1405/05/06",
            "dayOfWeek": "سه شنبه",
            "selectedPlanDetailId": None,
            "foods": [
                {
                    "planDetailId": 301,
                    "foodName": "واویشکا",
                    "remainCount": 10,
                },
            ],
        },
    ]

    resolved_tuesday = (
        service._infer_menu_date_from_days(
            "برای سه شنبه واویشکا رزرو کن",
            sample_days,
        )
    )

    if resolved_tuesday != "1405/05/06":
        raise RuntimeError(
            "Tuesday date resolution failed: "
            f"{resolved_tuesday!r}"
        )

    waavishka = (
        service._find_food_candidates_in_days(
            "برای سه شنبه واویشکا رزرو کن",
            sample_days,
            "1405/05/06",
        )
    )

    if (
        len(waavishka) != 1
        or waavishka[0][
            "food"
        ].get("foodName")
        != "واویشکا"
    ):
        raise RuntimeError(
            "Exact Waavishka match failed"
        )

    gheimeh = (
        service._find_food_candidates_in_days(
            (
                "برای یکشنبه قیمه سیب "
                "زمینی رو ثبت کن"
            ),
            sample_days,
            "1405/05/04",
        )
    )

    if (
        len(gheimeh) != 1
        or gheimeh[0][
            "food"
        ].get("foodName")
        != "قیمه سیب زمینی"
    ):
        raise RuntimeError(
            "Exact Gheimeh match failed"
        )

    greek_rice = (
        service._find_food_candidates_in_days(
            "پلو یونانی ثبت شه",
            sample_days,
            "1405/05/05",
        )
    )

    if (
        len(greek_rice) != 1
        or greek_rice[0][
            "food"
        ].get("foodName")
        != "پلو یونانی"
    ):
        raise RuntimeError(
            "Exact Greek rice match failed"
        )

    unknown_food = (
        service._find_food_candidates_in_days(
            "برای سه شنبه قرمه سبزی رزرو کن",
            sample_days,
            "1405/05/06",
        )
    )

    if unknown_food:
        raise RuntimeError(
            "Unknown food matched incorrectly"
        )

    unknown_tokens = (
        service._requested_food_tokens(
            "برای سه شنبه قرمه سبزی رزرو کن"
        )
    )

    if not {
        "قرمه",
        "سبزی",
    }.issubset(
        unknown_tokens
    ):
        raise RuntimeError(
            "Requested food token extraction failed"
        )

    generic_tokens = (
        service._requested_food_tokens(
            "برای فردا غذا رزرو کن"
        )
    )

    if generic_tokens:
        raise RuntimeError(
            "Generic reservation was treated "
            "as a named-food request: "
            f"{generic_tokens}"
        )

    if old_candidate_fallback in text:
        raise RuntimeError(
            "Unsafe date fallback still exists"
        )

    print("PATCH_OK")
    print("PART2_TESTS_OK")
    print(f"BACKUP={BACKUP}")

except Exception:
    CHAT.write_text(
        original_text,
        encoding="utf-8",
    )

    print("PATCH_FAILED_ROLLED_BACK")
    raise