from pathlib import Path
import importlib
import py_compile
import re
import shutil
import sys


ROOT = Path(r"D:\serviceAi")

CHAT = (
    ROOT
    / "app"
    / "application"
    / "services"
    / "chat_service.py"
)

FOOD = (
    ROOT
    / "app"
    / "application"
    / "services"
    / "food_service.py"
)

NLU = (
    ROOT
    / "app"
    / "application"
    / "services"
    / "nlu_core.py"
)

CHAT_BACKUP = CHAT.with_name(
    CHAT.name
    + ".bak_before_food_recommendation_v3"
)

FOOD_BACKUP = FOOD.with_name(
    FOOD.name
    + ".bak_before_food_recommendation_v3"
)

NLU_BACKUP = NLU.with_name(
    NLU.name
    + ".bak_before_food_recommendation_v3"
)

MARKER = "FOOD_RECOMMENDATION_V3"


def fail(message: str) -> None:
    raise RuntimeError(message)


def replace_pattern(
    text: str,
    pattern: re.Pattern[str],
    replacement: str,
    label: str,
) -> str:
    updated, count = pattern.subn(
        lambda _match: replacement,
        text,
        count=1,
    )

    if count != 1:
        fail(
            f"ANCHOR_NOT_FOUND_OR_DUPLICATE: "
            f"{label} count={count}"
        )

    return updated


chat_text = CHAT.read_text(
    encoding="utf-8-sig"
)

food_text = FOOD.read_text(
    encoding="utf-8-sig"
)

nlu_text = NLU.read_text(
    encoding="utf-8-sig"
)

marker_count = sum(
    MARKER in value
    for value in (
        chat_text,
        food_text,
        nlu_text,
    )
)

if marker_count == 3:
    print("ALREADY_PATCHED")
    raise SystemExit(0)

if marker_count:
    fail(
        "PARTIAL_PATCH_DETECTED"
    )


shutil.copy2(
    CHAT,
    CHAT_BACKUP,
)

shutil.copy2(
    FOOD,
    FOOD_BACKUP,
)

shutil.copy2(
    NLU,
    NLU_BACKUP,
)


# ==================================================
# FoodService:
# weekly menu + real personal/public insights
# ==================================================

food_anchor = (
    "    async def recommend_food("
)

food_anchor_index = food_text.find(
    food_anchor
)

if food_anchor_index < 0:
    fail(
        "ANCHOR_NOT_FOUND: "
        "FoodService.recommend_food"
    )


food_insights_method = '''
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

                if (
                    public_reservation
                    is not None
                    or average_rate
                    is not None
                ):
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

        if scored_items:
            best_item = max(
                scored_items,
                key=lambda item: (
                    item[0],
                    item[1],
                    item[2],
                ),
            )

            if best_item[0] > 0:
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


'''


food_text = (
    food_text[
        :food_anchor_index
    ]
    + food_insights_method
    + food_text[
        food_anchor_index:
    ]
)


# ==================================================
# ChatService:
# use enriched seven-day menu
# ==================================================

menu_branch_pattern = re.compile(
    r"        if \(\n"
    r"            menu_intent\n"
    r"            and not reservation_intent\n"
    r"            and not recommendation_intent\n"
    r"        \):\n"
    r".*?"
    r"(?="
    r"        if \(\n"
    r"            recommendation_intent\n"
    r")",
    re.DOTALL,
)


new_menu_branch = '''        if (
            menu_intent
            and not reservation_intent
            and not recommendation_intent
        ):
            # FOOD_RECOMMENDATION_V3
            menu = (
                await self.food
                .get_weekly_menu_insights(
                    context,
                    (
                        str(target_date)
                        if target_date
                        else None
                    ),
                    max_days=7,
                )
            )

            days = self._filter_menu_days(
                menu.get("days")
                or [],
                (
                    str(target_date)
                    if target_date
                    else None
                ),
                text,
            )

            return {
                "reply": (
                    self._menu_reply(
                        days
                    )
                ),
                "requiresConfirmation": False,
                "data": {
                    **menu,
                    "restaurant": (
                        restaurant_data
                    ),
                    "days": days,
                },
            }

'''


chat_text = replace_pattern(
    chat_text,
    menu_branch_pattern,
    new_menu_branch,
    "food menu branch",
)


# ==================================================
# ChatService:
# final menu presentation
# ==================================================

menu_reply_pattern = re.compile(
    r"    @staticmethod\n"
    r"    def _menu_reply\(\n"
    r".*?"
    r"(?="
    r"\n    @staticmethod\n"
    r"    def _reservation_status_reply\("
    r")",
    re.DOTALL,
)


new_menu_reply = '''    @staticmethod
    def _menu_reply(
        days: list[dict[str, Any]],
    ) -> str:
        # FOOD_RECOMMENDATION_V3
        if not days:
            return (
                "برای تاریخ موردنظر "
                "منویی پیدا نشد."
            )

        lines: list[str] = [
            (
                "منوی این هفته:"
                if len(days) > 1
                else "منوی غذا:"
            )
        ]

        personal_best = None
        public_best = None

        for day in days:
            day_label = str(
                day.get("dayOfWeek")
                or day.get("date")
                or "این روز"
            ).strip()

            date_value = str(
                day.get("date")
                or ""
            ).strip()

            if (
                date_value
                and date_value
                not in day_label
            ):
                label = (
                    f"{day_label} "
                    f"{date_value}"
                )
            else:
                label = day_label

            foods = [
                dict(food)
                for food in (
                    day.get("foods")
                    or []
                )
                if isinstance(
                    food,
                    dict,
                )
            ]

            selected_id = str(
                day.get(
                    "selectedPlanDetailId"
                )
                or ""
            ).strip()

            lines.append("")
            lines.append(label)

            if selected_id:
                selected_name = next(
                    (
                        str(
                            food.get(
                                "foodName"
                            )
                            or ""
                        ).strip()
                        for food in foods
                        if str(
                            food.get(
                                "planDetailId"
                            )
                            or ""
                        ).strip()
                        == selected_id
                    ),
                    "",
                )

                lines.append(
                    "✅ قبلاً رزرو "
                    "کرده‌اید: "
                    + (
                        selected_name
                        or "غذای رزروشده"
                    )
                )
                continue

            available_count = 0

            for food in foods:
                food_name = str(
                    food.get("foodName")
                    or ""
                ).strip()

                if not food_name:
                    continue

                remain_count = parse_int(
                    food.get(
                        "remainCount"
                    )
                )

                if (
                    remain_count
                    is not None
                    and remain_count <= 0
                ):
                    continue

                available_count += 1

                details = [
                    f"• {food_name}"
                ]

                interest = food.get(
                    "personalInterestPercent"
                )

                if interest is None:
                    details.append(
                        "علاقه شما: "
                        "سابقه کافی نیست"
                    )
                else:
                    details.append(
                        "علاقه شما: "
                        f"{int(interest)}٪"
                    )

                public_percent = food.get(
                    "publicReservationPercent"
                )

                if public_percent is not None:
                    details.append(
                        "رزرو عمومی: "
                        f"{int(public_percent)}٪ "
                        "از ظرفیت"
                    )

                average_rate = food.get(
                    "averageRate"
                )

                vote_count = (
                    parse_int(
                        food.get(
                            "voteCount"
                        )
                    )
                    or 0
                )

                if average_rate is not None:
                    try:
                        rate_text = (
                            f"{float(average_rate):g}"
                        )
                    except (
                        TypeError,
                        ValueError,
                    ):
                        rate_text = str(
                            average_rate
                        )

                    rating_text = (
                        "امتیاز عمومی: "
                        f"{rate_text} از ۵"
                    )

                    if vote_count:
                        rating_text += (
                            f" ({vote_count} رأی)"
                        )

                    details.append(
                        rating_text
                    )

                if food.get(
                    "isRecommended"
                ):
                    details.append(
                        "⭐ پیشنهاد برای شما"
                    )

                    personal_best = {
                        "name": food_name,
                        "date": date_value,
                        "day": day_label,
                        "interest": interest,
                    }

                if food.get(
                    "isPublicFavorite"
                ):
                    details.append(
                        "🔥 محبوب‌ترین انتخاب عمومی"
                    )

                    public_best = {
                        "name": food_name,
                        "date": date_value,
                        "day": day_label,
                        "publicPercent": (
                            public_percent
                        ),
                        "averageRate": (
                            average_rate
                        ),
                    }

                lines.append(
                    " — ".join(
                        details
                    )
                )

            if not available_count:
                lines.append(
                    "• غذای قابل رزروی "
                    "اعلام نشده است."
                )

        if personal_best:
            lines.extend(
                [
                    "",
                    (
                        "⭐ پیشنهاد شخصی هفته: "
                        f"{personal_best['name']} "
                        f"برای "
                        f"{personal_best['day']} "
                        f"{personal_best['date']}"
                    ).strip(),
                ]
            )

        if public_best:
            public_parts = [
                (
                    "🔥 محبوب‌ترین غذای "
                    "قابل رزرو: "
                    f"{public_best['name']}"
                )
            ]

            if (
                public_best[
                    "publicPercent"
                ]
                is not None
            ):
                public_parts.append(
                    (
                        f"{int(public_best['publicPercent'])}"
                        "٪ ظرفیت آن رزرو شده"
                    )
                )

            if (
                public_best[
                    "averageRate"
                ]
                is not None
            ):
                try:
                    public_rate = (
                        f"{float(public_best['averageRate']):g}"
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    public_rate = str(
                        public_best[
                            "averageRate"
                        ]
                    )

                public_parts.append(
                    (
                        "امتیاز متوسط "
                        f"{public_rate} از ۵"
                    )
                )

            lines.extend(
                [
                    "",
                    " — ".join(
                        public_parts
                    ),
                ]
            )

        return "\\n".join(lines)
'''


chat_text = replace_pattern(
    chat_text,
    menu_reply_pattern,
    new_menu_reply,
    "_menu_reply",
)


# ==================================================
# NLU:
# recognize colloquial food menu/reservation
# ==================================================

nlu_food_pattern = re.compile(
    r"def _detect_food_intent\(\n"
    r".*?"
    r"(?="
    r"\n\ndef _detect_leave_intent\("
    r")",
    re.DOTALL,
)


new_nlu_food = '''def _detect_food_intent(
    text: str,
) -> tuple[str, str] | None:
    # FOOD_RECOMMENDATION_V3
    has_food_word = _contains_any_word(
        text,
        _FOOD_WORDS,
    )

    has_reserve_word = _contains_any_word(
        text,
        _RESERVE_WORDS,
    )

    has_cancel_word = _contains_any_word(
        text,
        _CANCEL_WORDS,
    )

    has_reservation_word = (
        _contains_word(
            text,
            "رزرو",
        )
        or _contains_word(
            text,
            "رزروها",
        )
        or _contains_word(
            text,
            "رزروهای",
        )
    )

    has_order_word = (
        _contains_word(
            text,
            "سفارش",
        )
    )

    reserve_command_words = {
        "کن",
        "کنم",
        "بده",
        "بگیر",
        "بگیرم",
        "بگیری",
        "شه",
        "شود",
    }

    if (
        has_cancel_word
        and (
            has_food_word
            or has_reservation_word
        )
    ):
        return (
            "FOOD",
            "CANCEL_FOOD",
        )

    reservation_status_phrases = {
        "چی رزرو کردم",
        "چه چیزی رزرو کردم",
        "چی برام رزرو شده",
        "رزرو من",
        "رزرو شده",
        "غذای رزرو شده",
    }

    if _contains_any_phrase(
        text,
        reservation_status_phrases,
    ):
        return (
            "FOOD",
            "SHOW_FOOD_RESERVATION",
        )

    register_food_phrases = {
        "ثبت غذا",
        "غذا ثبت شه",
        "غذا ثبت شود",
        "غذا رو ثبت کن",
        "غذا را ثبت کن",
        "غذا انتخاب شه",
        "غذا انتخاب شود",
        "غذا رو انتخاب کن",
        "غذا را انتخاب کن",
        "برام غذا بگیر",
        "برایم غذا بگیر",
    }

    if (
        (
            (
                has_reservation_word
                or has_order_word
            )
            and _contains_any_word(
                text,
                reserve_command_words,
            )
        )
        or (
            has_food_word
            and has_reserve_word
        )
        or _contains_any_phrase(
            text,
            register_food_phrases,
        )
    ):
        return (
            "FOOD",
            "RESERVE_FOOD",
        )

    menu_phrases = {
        "چه غذایی",
        "چه غذا",
        "چی داریم",
        "ناهارهای این هفته",
        "منوی غذا",
        "غذا رو نشون بده",
        "غذا را نشان بده",
        "غذای امروز رو نشون بده",
        "غذای فردا رو نشون بده",
    }

    show_words = set(
        _SHOW_WORDS
    ) | {
        "نشون",
        "ببین",
        "بیار",
    }

    if (
        _contains_word(
            text,
            "منو",
        )
        or (
            has_food_word
            and (
                _contains_any_word(
                    text,
                    show_words,
                )
                or _contains_any_phrase(
                    text,
                    menu_phrases,
                )
            )
        )
    ):
        return (
            "FOOD",
            "SHOW_FOOD_MENU",
        )

    if has_food_word:
        return (
            "FOOD",
            "FOOD_UNKNOWN",
        )

    return None
'''


nlu_text = replace_pattern(
    nlu_text,
    nlu_food_pattern,
    new_nlu_food,
    "_detect_food_intent",
)


# ==================================================
# Write, compile and smoke-test
# ==================================================

try:
    CHAT.write_text(
        chat_text,
        encoding="utf-8",
    )

    FOOD.write_text(
        food_text,
        encoding="utf-8",
    )

    NLU.write_text(
        nlu_text,
        encoding="utf-8",
    )

    for path in (
        CHAT,
        FOOD,
        NLU,
    ):
        py_compile.compile(
            str(path),
            doraise=True,
        )

    sys.path.insert(
        0,
        str(ROOT),
    )

    importlib.invalidate_caches()

    nlu_module = importlib.import_module(
        "app.application.services.nlu_core"
    )

    tests = {
        (
            "برای سه شنبه "
            "واویشکا رزرو کن"
        ): (
            "FOOD",
            "RESERVE_FOOD",
        ),
        (
            "غذای یکشنبه "
            "4 مرداد رو نشون بده"
        ): (
            "FOOD",
            "SHOW_FOOD_MENU",
        ),
        "منوی غذا": (
            "FOOD",
            "SHOW_FOOD_MENU",
        ),
    }

    for phrase, expected in (
        tests.items()
    ):
        actual = (
            nlu_module
            ._detect_food_intent(
                nlu_module
                .normalize_text(
                    phrase
                )
            )
        )

        if actual != expected:
            fail(
                "NLU_SMOKE_TEST_FAILED: "
                f"{phrase} "
                f"actual={actual} "
                f"expected={expected}"
            )

except Exception:
    shutil.copy2(
        CHAT_BACKUP,
        CHAT,
    )

    shutil.copy2(
        FOOD_BACKUP,
        FOOD,
    )

    shutil.copy2(
        NLU_BACKUP,
        NLU,
    )

    raise


print("PATCH_OK")
print("NLU_TESTS_OK")
print(f"CHAT_BACKUP={CHAT_BACKUP}")
print(f"FOOD_BACKUP={FOOD_BACKUP}")
print(f"NLU_BACKUP={NLU_BACKUP}")