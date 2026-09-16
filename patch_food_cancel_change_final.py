# -*- coding: utf-8 -*-

from __future__ import annotations

import asyncio
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

ACTION = (
    ROOT
    / "app"
    / "application"
    / "services"
    / "action_service.py"
)

CHAT_BACKUP = CHAT.with_name(
    "chat_service.py.bak_before_food_cancel_change_final"
)

ACTION_BACKUP = ACTION.with_name(
    "action_service.py.bak_before_food_cancel_change_final"
)

CHAT_MARKER = "# FOOD_CANCEL_CHANGE_FINAL_V1"
ACTION_MARKER = "# FOOD_CHANGE_ACTION_FINAL_V1"


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

if not ACTION.exists():
    raise FileNotFoundError(ACTION)


original_chat = CHAT.read_text(
    encoding="utf-8-sig"
)

original_action = ACTION.read_text(
    encoding="utf-8-sig"
)

chat_text = original_chat
action_text = original_action


try:
    if not CHAT_BACKUP.exists():
        shutil.copy2(
            CHAT,
            CHAT_BACKUP,
        )

    if not ACTION_BACKUP.exists():
        shutil.copy2(
            ACTION,
            ACTION_BACKUP,
        )

    # =================================================
    # CHAT SERVICE
    # =================================================

    if CHAT_MARKER not in chat_text:
        # ---------------------------------------------
        # 1. Handle explicit cancel/change before Guard.
        # ---------------------------------------------

        guard_anchor = """        # FOOD_FINAL_PART1_ORDER_V1
        intent_decision = self.intent_guard.analyze(
"""

        require_once(
            chat_text,
            guard_anchor,
            "final part1 guard anchor",
        )

        guard_replacement = f"""        {CHAT_MARKER}
        food_mutation_response = (
            await self._handle_explicit_food_mutation(
                context,
                text,
                conversation_payload,
                selected_restaurant,
            )
        )

        if food_mutation_response is not None:
            return food_mutation_response

{guard_anchor}"""

        chat_text = chat_text.replace(
            guard_anchor,
            guard_replacement,
            1,
        )

        # ---------------------------------------------
        # 2. Add explicit food cancellation/change
        #    helpers before the existing Food Router.
        # ---------------------------------------------

        helper_anchor = """    def _override_explicit_food_command(
"""

        require_once(
            chat_text,
            helper_anchor,
            "food router helper anchor",
        )

        helper_code = r'''    @staticmethod
    def _food_mutation_kind(
        text: str,
    ) -> str | None:
        normalized = normalize_nlu_text(
            text or ""
        )

        change_terms = (
            "تغییر بده",
            "تغییرش بده",
            "تغییر کن",
            "عوض کن",
            "عوضش کن",
            "جایگزین",
            "جایگزین کن",
            "جایگزینش کن",
            "به جای",
            "بجای",
            "بجاش",
            "بکن",
            "تبدیل کن",
            "بردار و",
        )

        cancel_terms = (
            "حذف کن",
            "حذفش کن",
            "حذف شه",
            "حذف شود",
            "لغو کن",
            "لغوش کن",
            "لغو شه",
            "لغو شود",
            "کنسل کن",
            "کنسلش کن",
            "بردار",
            "برش دار",
            "پاک کن",
            "نمیخوام",
            "نمی خواهم",
        )

        if any(
            term in normalized
            for term in change_terms
        ):
            return "change"

        if any(
            term in normalized
            for term in cancel_terms
        ):
            return "cancel"

        return None

    @staticmethod
    def _normalize_food_mutation_text(
        text: str,
    ) -> str:
        normalized = normalize_nlu_text(
            text or ""
        )

        typo_replacements = {
            "یکشنیه": "یکشنبه",
            "یکشنیه": "یکشنبه",
            "یکشبه": "یکشنبه",
            "دوشنبه": "دوشنبه",
            "سهشنه": "سه شنبه",
            "سهشنیه": "سه شنبه",
            "چهارشنه": "چهارشنبه",
            "پنجشنه": "پنجشنبه",
        }

        for wrong, correct in (
            typo_replacements.items()
        ):
            normalized = normalized.replace(
                wrong,
                correct,
            )

        return normalized

    @staticmethod
    def _food_name_match_score(
        text: str,
        food_name: str,
    ) -> int:
        normalized_text = (
            ChatService
            ._normalize_food_mutation_text(
                text
            )
        )

        normalized_name = normalize_nlu_text(
            food_name or ""
        ).strip()

        if not normalized_name:
            return 0

        score = 0

        if normalized_name in normalized_text:
            score += 100

        name_tokens = set(
            re.findall(
                r"[a-zA-Z]+|[0-9]+|"
                r"[\u0600-\u06FF]+",
                normalized_name,
            )
        )

        ignored_tokens = {
            "غذا",
            "غذای",
            "خورشت",
            "خوراک",
            "پلو",
            "با",
            "و",
        }

        useful_tokens = {
            token
            for token in name_tokens
            if token not in ignored_tokens
            and not token.isdigit()
            and len(token) >= 3
        }

        for token in useful_tokens:
            if token in normalized_text:
                score += 15

        if useful_tokens and all(
            token in normalized_text
            for token in useful_tokens
        ):
            score += 30

        return score

    @classmethod
    def _foods_mentioned_in_text(
        cls,
        text: str,
        days: list[dict[str, Any]],
    ) -> list[
        tuple[
            int,
            dict[str, Any],
            dict[str, Any],
        ]
    ]:
        matches: list[
            tuple[
                int,
                dict[str, Any],
                dict[str, Any],
            ]
        ] = []

        for day in days:
            if not isinstance(day, dict):
                continue

            for food in (
                day.get("foods")
                or []
            ):
                if not isinstance(food, dict):
                    continue

                score = (
                    cls._food_name_match_score(
                        text,
                        str(
                            food.get(
                                "foodName"
                            )
                            or ""
                        ),
                    )
                )

                if score <= 0:
                    continue

                matches.append(
                    (
                        score,
                        dict(day),
                        dict(food),
                    )
                )

        matches.sort(
            key=lambda item: (
                item[0],
                str(
                    item[1].get("date")
                    or ""
                ),
            ),
            reverse=True,
        )

        return matches

    @classmethod
    def _resolve_food_mutation_day(
        cls,
        text: str,
        days: list[dict[str, Any]],
        reference_date: str,
    ) -> dict[str, Any] | None:
        normalized = (
            cls._normalize_food_mutation_text(
                text
            )
        )

        compact_text = re.sub(
            r"\s+",
            "",
            normalized,
        )

        # Exact Jalali date from menu.
        for day in days:
            if not isinstance(day, dict):
                continue

            date_value = str(
                day.get("date")
                or ""
            ).strip()

            if not date_value:
                continue

            compact_date = re.sub(
                r"\s+",
                "",
                date_value,
            )

            if (
                date_value in normalized
                or compact_date in compact_text
            ):
                return dict(day)

        # Explicit weekday, including common typos.
        requested_weekday = (
            cls._requested_weekday(
                normalized
            )
        )

        if requested_weekday:
            resolved_date = (
                cls._infer_menu_date_from_days(
                    normalized,
                    days,
                )
            )

            if resolved_date:
                for day in days:
                    if (
                        isinstance(day, dict)
                        and str(
                            day.get("date")
                            or ""
                        )
                        == str(resolved_date)
                    ):
                        return dict(day)

        # Relative date such as today/tomorrow.
        try:
            date_nlu = analyze_message(
                normalized,
                reference_date=(
                    reference_date
                ),
                conversation_state=None,
            )

            entities = (
                date_nlu.get("entities")
                if isinstance(
                    date_nlu.get(
                        "entities"
                    ),
                    dict,
                )
                else {}
            )

            nlu_date = str(
                entities.get("date")
                or entities.get(
                    "startDate"
                )
                or ""
            ).strip()

            if nlu_date:
                for day in days:
                    if (
                        isinstance(day, dict)
                        and str(
                            day.get("date")
                            or ""
                        )
                        == nlu_date
                    ):
                        return dict(day)

        except Exception:
            pass

        # When only one active reservation exists,
        # allow phrases such as "رزرو غذام رو حذف کن".
        selected_days = [
            dict(day)
            for day in days
            if isinstance(day, dict)
            and parse_int(
                day.get(
                    "selectedPlanDetailId"
                )
            )
            not in {
                None,
                0,
            }
        ]

        if len(selected_days) == 1:
            return selected_days[0]

        return None

    async def _handle_explicit_food_mutation(
        self,
        context: AgentContext,
        text: str,
        conversation_payload: dict[str, Any],
        selected_restaurant: (
            dict[str, Any]
            | None
        ),
    ) -> dict[str, Any] | None:
        mutation_kind = (
            self._food_mutation_kind(
                text
            )
        )

        if mutation_kind is None:
            return None

        normalized = (
            self._normalize_food_mutation_text(
                text
            )
        )

        other_domain_terms = (
            "مرخصی",
            "ماموریت",
            "مأموریت",
            "تردد",
            "ورود",
            "خروج",
            "اضافه کاری",
            "اضافه‌کاری",
        )

        if any(
            term in normalized
            for term in other_domain_terms
        ):
            return None

        restaurant = (
            selected_restaurant
            if isinstance(
                selected_restaurant,
                dict,
            )
            else (
                conversation_payload.get(
                    "restaurant"
                )
                if isinstance(
                    conversation_payload.get(
                        "restaurant"
                    ),
                    dict,
                )
                else {}
            )
        )

        restaurant_id = (
            parse_int(
                context.restaurant_id
            )
            or parse_int(
                restaurant.get(
                    "restaurantId"
                )
            )
        )

        food_context = context

        if restaurant_id is None:
            restaurants = (
                await self.food
                .get_my_restaurants(
                    context
                )
            )

            safe_restaurants = [
                dict(item)
                for item in restaurants
                if isinstance(item, dict)
                and parse_int(
                    item.get(
                        "restaurantId"
                    )
                )
                is not None
            ]

            if len(safe_restaurants) == 1:
                restaurant = (
                    safe_restaurants[0]
                )

                restaurant_id = parse_int(
                    restaurant.get(
                        "restaurantId"
                    )
                )

            elif len(safe_restaurants) > 1:
                names = [
                    str(
                        item.get(
                            "restaurantName"
                        )
                        or (
                            "رستوران "
                            + str(
                                item.get(
                                    "restaurantId"
                                )
                            )
                        )
                    )
                    for item in (
                        safe_restaurants
                    )
                ]

                return {
                    "reply": (
                        "برای حذف یا تغییر غذا، "
                        "ابتدا رستوران را مشخص کنید: "
                        + "، ".join(names)
                    ),
                    "requiresConfirmation": False,
                    "data": {
                        "restaurants": (
                            safe_restaurants
                        ),
                    },
                }

            else:
                return {
                    "reply": (
                        "رستوران مجاز برای عملیات "
                        "غذا پیدا نشد."
                    ),
                    "requiresConfirmation": False,
                }

        if restaurant_id is None:
            return {
                "reply": (
                    "شناسه رستوران برای عملیات "
                    "غذا مشخص نیست."
                ),
                "requiresConfirmation": False,
            }

        food_context = context.model_copy(
            update={
                "restaurant_id": (
                    restaurant_id
                ),
                "meal_id": (
                    context.meal_id
                    or FOOD_MEAL_ID
                ),
            }
        )

        if not restaurant:
            restaurant = {
                "restaurantId": (
                    restaurant_id
                ),
                "restaurantName": "",
            }

        menu = await self.food.get_weekly_menu(
            food_context
        )

        days = [
            dict(day)
            for day in (
                menu.get("days")
                or []
            )
            if isinstance(day, dict)
        ]

        menu_mentions = (
            self._foods_mentioned_in_text(
                normalized,
                days,
            )
        )

        has_food_hint = any(
            word in normalized
            for word in (
                "غذا",
                "غذای",
                "رزرو",
                "ناهار",
                "منو",
            )
        )

        has_date_hint = bool(
            self._requested_weekday(
                normalized
            )
        ) or any(
            word in normalized
            for word in (
                "امروز",
                "فردا",
                "پس فردا",
                "پسفردا",
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
            )
        )

        if not (
            has_food_hint
            or has_date_hint
            or menu_mentions
        ):
            return None

        target_day = (
            self._resolve_food_mutation_day(
                normalized,
                days,
                str(
                    food_context.date
                    or ""
                ),
            )
        )

        if target_day is None:
            selected_days = [
                day
                for day in days
                if parse_int(
                    day.get(
                        "selectedPlanDetailId"
                    )
                )
                not in {
                    None,
                    0,
                }
            ]

            if selected_days:
                labels = [
                    (
                        str(
                            day.get(
                                "dayOfWeek"
                            )
                            or ""
                        )
                        + " "
                        + str(
                            day.get("date")
                            or ""
                        )
                    ).strip()
                    for day in selected_days
                ]

                return {
                    "reply": (
                        "مشخص کنید رزرو کدام روز "
                        "باید حذف یا تغییر کند: "
                        + "، ".join(labels)
                    ),
                    "requiresConfirmation": False,
                    "data": {
                        "days": selected_days,
                        "restaurant": restaurant,
                    },
                }

            return {
                "reply": (
                    "رزرو فعال غذایی برای حذف "
                    "یا تغییر پیدا نشد."
                ),
                "requiresConfirmation": False,
                "data": {
                    "days": [],
                    "restaurant": restaurant,
                },
            }

        target_date = str(
            target_day.get("date")
            or ""
        ).strip()

        day_label = str(
            target_day.get(
                "dayOfWeek"
            )
            or target_date
            or "روز موردنظر"
        ).strip()

        selected_id = parse_int(
            target_day.get(
                "selectedPlanDetailId"
            )
        )

        if (
            selected_id is None
            or selected_id == 0
        ):
            return {
                "reply": (
                    f"برای {day_label} "
                    "رزرو فعالی وجود ندارد."
                ),
                "requiresConfirmation": False,
                "data": {
                    "date": target_date,
                    "dayOfWeek": day_label,
                    "days": [target_day],
                    "restaurant": restaurant,
                },
            }

        foods = [
            dict(food)
            for food in (
                target_day.get("foods")
                or []
            )
            if isinstance(food, dict)
        ]

        selected_food = next(
            (
                food
                for food in foods
                if parse_int(
                    food.get(
                        "planDetailId"
                    )
                )
                == selected_id
            ),
            {},
        )

        selected_name = str(
            selected_food.get(
                "foodName"
            )
            or "غذای رزروشده"
        ).strip()

        target_mentions = (
            self._foods_mentioned_in_text(
                normalized,
                [target_day],
            )
        )

        if mutation_kind == "cancel":
            mentioned_ids = {
                parse_int(
                    food.get(
                        "planDetailId"
                    )
                )
                for _, _, food in (
                    target_mentions
                )
            }

            mentioned_ids.discard(None)
            mentioned_ids.discard(0)

            if (
                mentioned_ids
                and selected_id
                not in mentioned_ids
            ):
                mentioned_names = [
                    str(
                        food.get(
                            "foodName"
                        )
                        or ""
                    ).strip()
                    for _, _, food in (
                        target_mentions
                    )
                    if str(
                        food.get(
                            "foodName"
                        )
                        or ""
                    ).strip()
                ]

                return {
                    "reply": (
                        f"رزرو فعلی {day_label} "
                        f"«{selected_name}» است، نه "
                        f"«{'، '.join(mentioned_names)}». "
                        "برای جلوگیری از حذف اشتباه، "
                        f"بنویسید: {selected_name} "
                        f"{day_label} را حذف کن."
                    ),
                    "requiresConfirmation": False,
                    "data": {
                        "date": target_date,
                        "dayOfWeek": day_label,
                        "food": selected_food,
                        "restaurant": restaurant,
                    },
                }

            action_payload = {
                "planDetailId": selected_id,
                "restaurantId": (
                    restaurant_id
                ),
                "mealId": (
                    food_context.meal_id
                    or FOOD_MEAL_ID
                ),
            }

            action = (
                await self.actions
                .create_pending_action(
                    str(
                        food_context.employee_id
                    ),
                    "CANCEL_FOOD",
                    action_payload,
                )
            )

            response = {
                "reply": (
                    f"رزرو «{selected_name}» "
                    f"برای {day_label} لغو شود؟"
                ),
                "requiresConfirmation": True,
                "pendingAction": {
                    "id": action["id"],
                    "label": (
                        "تأیید و لغو رزرو غذا"
                    ),
                    "expiresAt": action.get(
                        "expiresAt"
                    ),
                },
                "data": {
                    "date": target_date,
                    "dayOfWeek": day_label,
                    "food": selected_food,
                    "restaurant": restaurant,
                    "days": [target_day],
                    "mealId": (
                        food_context.meal_id
                        or FOOD_MEAL_ID
                    ),
                },
            }

            mutation_intent = (
                "CANCEL_FOOD"
            )

        else:
            available_alternatives = []

            for food in foods:
                food_id = parse_int(
                    food.get(
                        "planDetailId"
                    )
                )

                if (
                    food_id is None
                    or food_id == 0
                    or food_id
                    == selected_id
                ):
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

                available_alternatives.append(
                    food
                )

            scored_alternatives = [
                (
                    self._food_name_match_score(
                        normalized,
                        str(
                            food.get(
                                "foodName"
                            )
                            or ""
                        ),
                    ),
                    food,
                )
                for food in (
                    available_alternatives
                )
            ]

            scored_alternatives = [
                item
                for item in scored_alternatives
                if item[0] > 0
            ]

            scored_alternatives.sort(
                key=lambda item: item[0],
                reverse=True,
            )

            if not scored_alternatives:
                names = [
                    str(
                        food.get(
                            "foodName"
                        )
                        or ""
                    ).strip()
                    for food in (
                        available_alternatives
                    )
                    if str(
                        food.get(
                            "foodName"
                        )
                        or ""
                    ).strip()
                ]

                reply = (
                    f"رزرو فعلی {day_label} "
                    f"«{selected_name}» است. "
                    "نام غذای جایگزین را مشخص کنید."
                )

                if names:
                    reply += (
                        " گزینه‌های قابل رزرو: "
                        + "، ".join(names)
                        + "."
                    )

                return {
                    "reply": reply,
                    "requiresConfirmation": False,
                    "data": {
                        "date": target_date,
                        "dayOfWeek": day_label,
                        "currentFood": (
                            selected_food
                        ),
                        "alternatives": (
                            available_alternatives
                        ),
                        "restaurant": restaurant,
                        "days": [target_day],
                    },
                }

            best_score = (
                scored_alternatives[0][0]
            )

            tied = [
                food
                for score, food in (
                    scored_alternatives
                )
                if score == best_score
            ]

            if len(tied) > 1:
                tied_names = [
                    str(
                        food.get(
                            "foodName"
                        )
                        or ""
                    ).strip()
                    for food in tied
                ]

                return {
                    "reply": (
                        "چند غذای جایگزین ممکن "
                        "پیدا شد. یکی را دقیق انتخاب کنید: "
                        + "، ".join(tied_names)
                    ),
                    "requiresConfirmation": False,
                    "data": {
                        "alternatives": tied,
                        "date": target_date,
                        "restaurant": restaurant,
                    },
                }

            new_food = tied[0]

            new_id = parse_int(
                new_food.get(
                    "planDetailId"
                )
            )

            new_name = str(
                new_food.get(
                    "foodName"
                )
                or "غذای جدید"
            ).strip()

            if (
                new_id is None
                or new_id == 0
            ):
                raise AppError(
                    "شناسه غذای جایگزین معتبر نیست.",
                    code=(
                        "INVALID_NEW_PLAN_DETAIL"
                    ),
                )

            action_payload = {
                "oldPlanDetailId": (
                    selected_id
                ),
                "newPlanDetailId": new_id,
                "restaurantId": (
                    restaurant_id
                ),
                "mealId": (
                    food_context.meal_id
                    or FOOD_MEAL_ID
                ),
                "targetDate": target_date,
                "oldFoodName": (
                    selected_name
                ),
                "newFoodName": new_name,
            }

            action = (
                await self.actions
                .create_pending_action(
                    str(
                        food_context.employee_id
                    ),
                    "CHANGE_FOOD",
                    action_payload,
                )
            )

            response = {
                "reply": (
                    f"رزرو «{selected_name}» "
                    f"{day_label} لغو و "
                    f"«{new_name}» رزرو شود؟"
                ),
                "requiresConfirmation": True,
                "pendingAction": {
                    "id": action["id"],
                    "label": (
                        "تأیید و تغییر رزرو غذا"
                    ),
                    "expiresAt": action.get(
                        "expiresAt"
                    ),
                },
                "data": {
                    "date": target_date,
                    "dayOfWeek": day_label,
                    "currentFood": (
                        selected_food
                    ),
                    "newFood": new_food,
                    "restaurant": restaurant,
                    "days": [target_day],
                    "mealId": (
                        food_context.meal_id
                        or FOOD_MEAL_ID
                    ),
                },
            }

            mutation_intent = (
                "CHANGE_FOOD"
            )

        mutation_nlu = {
            "domain": "FOOD",
            "intent": mutation_intent,
            "entities": {
                "date": target_date,
            },
            "confidence": 1.0,
            "missingFields": [],
            "needsClarification": False,
            "conversationComplete": False,
            "clarification": None,
            "errors": [],
            "state": {
                "domain": "FOOD",
                "intent": mutation_intent,
                "entities": {
                    "date": target_date,
                },
                "missingFields": [],
            },
        }

        return await self._finalize_response_state(
            food_context,
            mutation_nlu,
            conversation_payload,
            response,
            normalized,
        )

'''

        chat_text = chat_text.replace(
            helper_anchor,
            helper_code + helper_anchor,
            1,
        )

        # ---------------------------------------------
        # 3. Preserve conversation memory after a
        #    confirmed action succeeds.
        # ---------------------------------------------

        save_signature = """            await self._save_conversation_payload(
                context,
                {
                    "lastSuccessfulAction": {
"""

        save_start = chat_text.find(
            save_signature
        )

        if save_start < 0:
            raise RuntimeError(
                "successful action state block not found"
            )

        save_end = chat_text.find(
            "\n\n            return {",
            save_start,
        )

        if save_end < 0:
            raise RuntimeError(
                "successful action state block end not found"
            )

        new_save_block = """            success_payload = dict(
                conversation_payload
            )

            success_payload.pop(
                "pendingActionId",
                None,
            )

            success_payload.pop(
                "proposal",
                None,
            )

            success_payload.pop(
                "proposalRejected",
                None,
            )

            if pending_action.action_type in {
                "RESERVE_FOOD",
                "CANCEL_FOOD",
                "CHANGE_FOOD",
            }:
                success_payload[
                    "lastDomain"
                ] = "FOOD"

                # Menu selection data is now stale.
                # The next request must read fresh API data.
                success_payload.pop(
                    "recentMenus",
                    None,
                )

            success_payload[
                "lastSuccessfulAction"
            ] = {
                "actionId": (
                    pending_action.id
                ),
                "actionType": (
                    pending_action.action_type
                ),
                "status": success_status,
                "reply": success_reply,
                "data": success_data,
                "completedAtEpoch": (
                    time.time()
                ),
            }

            await self._save_conversation_payload(
                context,
                success_payload,
            )"""

        chat_text = (
            chat_text[:save_start]
            + new_save_block
            + chat_text[save_end:]
        )

        # ---------------------------------------------
        # 4. Success message for CHANGE_FOOD.
        # ---------------------------------------------

        success_message_anchor = """            "CANCEL_FOOD": (
                "رزرو غذا با موفقیت لغو شد."
            ),
"""

        require_once(
            chat_text,
            success_message_anchor,
            "chat action success message",
        )

        success_message_replacement = (
            success_message_anchor
            + """            "CHANGE_FOOD": (
                "رزرو غذا با موفقیت تغییر کرد."
            ),
"""
        )

        chat_text = chat_text.replace(
            success_message_anchor,
            success_message_replacement,
            1,
        )

    # =================================================
    # ACTION SERVICE
    # =================================================

    if ACTION_MARKER not in action_text:
        # ---------------------------------------------
        # 5. Add CHANGE_FOOD execution.
        # ---------------------------------------------

        cancel_branch = """        if action_type == "CANCEL_FOOD":
            food_context = self._food_context_from_payload(
                context,
                payload,
            )

            return await self.food.cancel_food(
                food_context,
                payload["planDetailId"],
                idempotency_key=idempotency_key,
            )

"""

        require_once(
            action_text,
            cancel_branch,
            "action cancel food branch",
        )

        change_branch = f'''        {ACTION_MARKER}
        if action_type == "CHANGE_FOOD":
            food_context = self._food_context_from_payload(
                context,
                payload,
            )

            old_plan_id = parse_int(
                payload.get(
                    "oldPlanDetailId"
                )
            )

            new_plan_id = parse_int(
                payload.get(
                    "newPlanDetailId"
                )
            )

            if (
                old_plan_id is None
                or old_plan_id == 0
            ):
                raise AppError(
                    "شناسه رزرو فعلی معتبر نیست.",
                    code="INVALID_OLD_PLAN_DETAIL",
                )

            if (
                new_plan_id is None
                or new_plan_id == 0
            ):
                raise AppError(
                    "شناسه غذای جایگزین معتبر نیست.",
                    code="INVALID_NEW_PLAN_DETAIL",
                )

            if old_plan_id == new_plan_id:
                raise AppError(
                    "غذای فعلی و غذای جایگزین یکسان هستند.",
                    code="SAME_FOOD_REPLACEMENT",
                )

            cancel_result = (
                await self.food.cancel_food(
                    food_context,
                    old_plan_id,
                    idempotency_key=(
                        f"{{idempotency_key}}:cancel"
                    ),
                )
            )

            try:
                reserve_result = (
                    await self.food.reserve_food(
                        food_context,
                        new_plan_id,
                        idempotency_key=(
                            f"{{idempotency_key}}:reserve"
                        ),
                    )
                )

            except IntegrationError as exc:
                if (
                    exc.code
                    in UNCERTAIN_INTEGRATION_CODES
                ):
                    # The new reservation may have reached
                    # the downstream service. Do not attempt
                    # an unsafe automatic rollback.
                    raise

                reserve_error = exc

            except Exception as exc:
                reserve_error = exc

            else:
                return {{
                    "changed": True,
                    "targetDate": payload.get(
                        "targetDate"
                    ),
                    "oldFoodName": payload.get(
                        "oldFoodName"
                    ),
                    "newFoodName": payload.get(
                        "newFoodName"
                    ),
                    "oldPlanDetailId": (
                        old_plan_id
                    ),
                    "newPlanDetailId": (
                        new_plan_id
                    ),
                    "cancelResult": (
                        cancel_result
                    ),
                    "reserveResult": (
                        reserve_result
                    ),
                }}

            try:
                rollback_result = (
                    await self.food.reserve_food(
                        food_context,
                        old_plan_id,
                        idempotency_key=(
                            f"{{idempotency_key}}:rollback"
                        ),
                    )
                )

            except Exception as rollback_exc:
                raise AppError(
                    (
                        "رزرو قبلی لغو شد، اما رزرو "
                        "غذای جدید و بازگردانی رزرو "
                        "قبلی هر دو ناموفق بودند. "
                        "وضعیت رزرو را بررسی کنید."
                    ),
                    status_code=409,
                    code=(
                        "FOOD_CHANGE_PARTIAL_FAILURE"
                    ),
                    details={{
                        "targetDate": payload.get(
                            "targetDate"
                        ),
                        "oldFoodName": payload.get(
                            "oldFoodName"
                        ),
                        "newFoodName": payload.get(
                            "newFoodName"
                        ),
                        "reserveError": (
                            type(
                                reserve_error
                            ).__name__
                        ),
                        "rollbackError": (
                            type(
                                rollback_exc
                            ).__name__
                        ),
                    }},
                ) from reserve_error

            raise AppError(
                (
                    "رزرو غذای جدید انجام نشد؛ "
                    "رزرو قبلی با موفقیت بازگردانده شد."
                ),
                status_code=409,
                code="FOOD_CHANGE_ROLLED_BACK",
                details={{
                    "targetDate": payload.get(
                        "targetDate"
                    ),
                    "oldFoodName": payload.get(
                        "oldFoodName"
                    ),
                    "newFoodName": payload.get(
                        "newFoodName"
                    ),
                    "rollbackResult": (
                        rollback_result
                    ),
                }},
            ) from reserve_error

'''

        action_text = action_text.replace(
            cancel_branch,
            cancel_branch + change_branch,
            1,
        )

        # ---------------------------------------------
        # 6. Validate CHANGE_FOOD payload.
        # ---------------------------------------------

        validation_anchor = """            "CANCEL_FOOD": (
                "planDetailId",
            ),
"""

        require_once(
            action_text,
            validation_anchor,
            "action validation anchor",
        )

        validation_replacement = (
            validation_anchor
            + """            "CHANGE_FOOD": (
                "oldPlanDetailId",
                "newPlanDetailId",
            ),
"""
        )

        action_text = action_text.replace(
            validation_anchor,
            validation_replacement,
            1,
        )

    # =================================================
    # WRITE FILES
    # =================================================

    CHAT.write_text(
        chat_text,
        encoding="utf-8",
    )

    ACTION.write_text(
        action_text,
        encoding="utf-8",
    )

    # =================================================
    # SYNTAX TESTS
    # =================================================

    py_compile.compile(
        str(CHAT),
        doraise=True,
    )

    py_compile.compile(
        str(ACTION),
        doraise=True,
    )

    # =================================================
    # RUNTIME TESTS
    # =================================================

    sys.path.insert(
        0,
        str(ROOT),
    )

    from app.application.services.action_service import (
        ActionService,
    )

    from app.application.services.chat_service import (
        ChatService,
    )

    from app.core.exceptions import AppError

    from app.domain.models import AgentContext

    chat = object.__new__(
        ChatService
    )

    sample_days = [
        {
            "date": "1405/05/04",
            "dayOfWeek": "یکشنبه",
            "selectedPlanDetailId": (
                -2147483225
            ),
            "foods": [
                {
                    "planDetailId": (
                        -2147483225
                    ),
                    "foodName": (
                        "قیمه سیب زمینی"
                    ),
                    "remainCount": 111,
                },
                {
                    "planDetailId": (
                        -2147483224
                    ),
                    "foodName": "کوبیده",
                    "remainCount": 111,
                },
                {
                    "planDetailId": (
                        -2147483223
                    ),
                    "foodName": (
                        "جوجه با استخوان"
                    ),
                    "remainCount": 111,
                },
            ],
        },
    ]

    cancel_cases = [
        "برای یکشنبه قیمه سیب زمینی رو حذف کن",
        "قیمه یکشنبه رو لغو کن",
        "رزرو غذای یکشنبه رو کنسل کن",
        "غذای یکشنبه رو بردار",
    ]

    for message in cancel_cases:
        if (
            chat._food_mutation_kind(
                message
            )
            != "cancel"
        ):
            raise RuntimeError(
                "Cancel phrase not detected: "
                f"{message!r}"
            )

    change_cases = [
        (
            "برای یکشنبه قیمه رو تغییر بده "
            "و بکن کوبیده"
        ),
        "قیمه رو عوض کن با کوبیده",
        "به جای قیمه کوبیده بزن",
        "کوبیده رو جایگزین قیمه کن",
        "غذای یکشنبه رو به کوبیده تغییر بده",
    ]

    for message in change_cases:
        if (
            chat._food_mutation_kind(
                message
            )
            != "change"
        ):
            raise RuntimeError(
                "Change phrase not detected: "
                f"{message!r}"
            )

        koobideh_score = (
            chat._food_name_match_score(
                message,
                "کوبیده",
            )
        )

        if koobideh_score <= 0:
            raise RuntimeError(
                "New food name not detected: "
                f"{message!r}"
            )

    typo_day = (
        chat._resolve_food_mutation_day(
            (
                "برای یکشنیه قیمه رو "
                "تغییر بده و بکن کوبیده"
            ),
            sample_days,
            "1405/05/01",
        )
    )

    if (
        not typo_day
        or typo_day.get("date")
        != "1405/05/04"
    ):
        raise RuntimeError(
            "Weekday typo resolution failed"
        )

    mentioned = (
        chat._foods_mentioned_in_text(
            (
                "قیمه رو تغییر بده "
                "و بکن کوبیده"
            ),
            sample_days,
        )
    )

    mentioned_names = {
        str(
            food.get("foodName")
            or ""
        )
        for _, _, food in mentioned
    }

    if not {
        "قیمه سیب زمینی",
        "کوبیده",
    }.issubset(
        mentioned_names
    ):
        raise RuntimeError(
            "Old/new food matching failed: "
            f"{mentioned_names!r}"
        )

    class FakeFood:
        def __init__(
            self,
            *,
            fail_new: bool = False,
            fail_rollback: bool = False,
        ) -> None:
            self.fail_new = fail_new
            self.fail_rollback = (
                fail_rollback
            )
            self.calls = []

        async def cancel_food(
            self,
            context,
            plan_detail_id,
            *,
            idempotency_key=None,
        ):
            self.calls.append(
                (
                    "cancel",
                    plan_detail_id,
                )
            )

            return {
                "cancelled": True,
                "planDetailId": (
                    plan_detail_id
                ),
            }

        async def reserve_food(
            self,
            context,
            plan_detail_id,
            *,
            idempotency_key=None,
        ):
            self.calls.append(
                (
                    "reserve",
                    plan_detail_id,
                )
            )

            if (
                plan_detail_id
                == -2147483224
                and self.fail_new
            ):
                raise AppError(
                    "رزرو جدید ناموفق",
                    code="TEST_NEW_FAILED",
                )

            if (
                plan_detail_id
                == -2147483225
                and self.fail_rollback
            ):
                raise AppError(
                    "بازگردانی ناموفق",
                    code="TEST_ROLLBACK_FAILED",
                )

            return {
                "reserved": True,
                "planDetailId": (
                    plan_detail_id
                ),
            }

    async def run_action_tests() -> None:
        context = AgentContext(
            employee_id="05000602",
            restaurant_id=84,
            meal_id=1,
        )

        payload = {
            "oldPlanDetailId": (
                -2147483225
            ),
            "newPlanDetailId": (
                -2147483224
            ),
            "restaurantId": 84,
            "mealId": 1,
            "targetDate": "1405/05/04",
            "oldFoodName": (
                "قیمه سیب زمینی"
            ),
            "newFoodName": "کوبیده",
        }

        ActionService._validate_payload(
            "CHANGE_FOOD",
            payload,
        )

        action = object.__new__(
            ActionService
        )

        action.food = FakeFood()

        result = await action._execute(
            context,
            "CHANGE_FOOD",
            payload,
            "test-change-success",
        )

        if result.get("changed") is not True:
            raise RuntimeError(
                "Successful food change "
                "did not return changed=True"
            )

        if action.food.calls != [
            (
                "cancel",
                -2147483225,
            ),
            (
                "reserve",
                -2147483224,
            ),
        ]:
            raise RuntimeError(
                "Food change call order failed: "
                f"{action.food.calls!r}"
            )

        rollback_action = object.__new__(
            ActionService
        )

        rollback_action.food = FakeFood(
            fail_new=True,
        )

        try:
            await rollback_action._execute(
                context,
                "CHANGE_FOOD",
                payload,
                "test-change-rollback",
            )

        except AppError as exc:
            if (
                getattr(
                    exc,
                    "code",
                    ""
                )
                != "FOOD_CHANGE_ROLLED_BACK"
            ):
                raise

        else:
            raise RuntimeError(
                "Failed new reservation did "
                "not trigger rollback error"
            )

        if rollback_action.food.calls != [
            (
                "cancel",
                -2147483225,
            ),
            (
                "reserve",
                -2147483224,
            ),
            (
                "reserve",
                -2147483225,
            ),
        ]:
            raise RuntimeError(
                "Food rollback call order failed: "
                f"{rollback_action.food.calls!r}"
            )

    asyncio.run(
        run_action_tests()
    )

    if CHAT_MARKER not in chat_text:
        raise RuntimeError(
            "Chat marker was not written"
        )

    if ACTION_MARKER not in action_text:
        raise RuntimeError(
            "Action marker was not written"
        )

    print("PATCH_OK")
    print("CANCEL_CHANGE_TESTS_OK")
    print(f"CHAT_BACKUP={CHAT_BACKUP}")
    print(f"ACTION_BACKUP={ACTION_BACKUP}")

except Exception:
    CHAT.write_text(
        original_chat,
        encoding="utf-8",
    )

    ACTION.write_text(
        original_action,
        encoding="utf-8",
    )

    print("PATCH_FAILED_ROLLED_BACK")
    raise