from pathlib import Path
import importlib
import py_compile
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

BACKUP = CHAT.with_name(
    CHAT.name
    + ".bak_before_food_router_v4"
)

MARKER = "FOOD_ROUTER_V4"


def replace_once(
    text: str,
    old: str,
    new: str,
    label: str,
) -> str:
    count = text.count(old)

    if count != 1:
        raise RuntimeError(
            f"ANCHOR_ERROR: {label} "
            f"count={count}"
        )

    return text.replace(
        old,
        new,
        1,
    )


text = CHAT.read_text(
    encoding="utf-8-sig"
)

if MARKER in text:
    print("ALREADY_PATCHED")
    raise SystemExit(0)

shutil.copy2(
    CHAT,
    BACKUP,
)

if MARKER in text:
    print("ALREADY_PATCHED")
    raise SystemExit(0)


shutil.copy2(
    CHAT,
    BACKUP,
)


# ==================================================
# 1. قطعی‌کردن Intent غذا پیش از needsClarification
# ==================================================

clarification_anchor = '''        if nlu_result.get(
            "needsClarification"
        ):
'''

clarification_replacement = '''        # FOOD_ROUTER_V4
        nlu_result = (
            self._override_explicit_food_command(
                nlu_result,
                combined_text,
                conversation_payload,
            )
        )

        if nlu_result.get(
            "needsClarification"
        ):
'''

text = replace_once(
    text,
    clarification_anchor,
    clarification_replacement,
    "clarification routing",
)


# ==================================================
# 2. Router قطعی برای نمایش، رزرو و لغو غذا
# ==================================================

helper_anchor = '''    @staticmethod
    def _is_food(text: str) -> bool:
'''

helper_code = '''    def _override_explicit_food_command(
        self,
        nlu_result: dict[str, Any],
        text: str,
        conversation_payload: dict[str, Any],
    ) -> dict[str, Any]:
        # FOOD_ROUTER_V4
        result = dict(
            nlu_result
            or {}
        )

        normalized = normalize_nlu_text(
            text
            or ""
        )

        food_candidates = (
            self._find_food_candidates(
                text,
                conversation_payload,
            )
        )

        has_candidate = bool(
            food_candidates
        )

        has_food_subject = any(
            word in normalized
            for word in [
                "غذا",
                "غذای",
                "غذاها",
                "منو",
                "ناهار",
                "خوراک",
            ]
        )

        reserve_phrases = [
            "رزرو کن",
            "رزرو شه",
            "رزرو شود",
            "ثبت کن",
            "ثبت شه",
            "ثبت شود",
            "انتخاب کن",
            "انتخاب شه",
            "انتخاب شود",
            "برام بگیر",
            "برایم بگیر",
            "سفارش بده",
        ]

        show_phrases = [
            "منو",
            "نشان بده",
            "نشون بده",
            "نشون",
            "نمایش بده",
            "لیست کن",
            "بگو",
            "چیه",
            "چی هست",
            "چه غذایی",
            "غذای امروز",
            "غذای فردا",
        ]

        cancel_phrases = [
            "لغو کن",
            "لغو شه",
            "لغو شود",
            "کنسل کن",
            "حذف کن",
        ]

        has_reserve_command = any(
            phrase in normalized
            for phrase in reserve_phrases
        )

        has_show_command = any(
            phrase in normalized
            for phrase in show_phrases
        )

        has_cancel_command = any(
            phrase in normalized
            for phrase in cancel_phrases
        )

        requested_weekday = (
            self._requested_weekday(
                text
            )
        )

        has_date_word = any(
            word in normalized
            for word in [
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
            ]
        )

        last_domain_is_food = (
            str(
                conversation_payload.get(
                    "lastDomain"
                )
                or ""
            )
            == "FOOD"
        )

        food_context = (
            has_food_subject
            or has_candidate
            or last_domain_is_food
        )

        intent = None

        if (
            has_cancel_command
            and food_context
        ):
            intent = "CANCEL_FOOD"

        elif (
            has_reserve_command
            and (
                food_context
                or bool(
                    requested_weekday
                )
                or has_date_word
            )
        ):
            intent = "RESERVE_FOOD"

        elif (
            has_show_command
            and (
                has_food_subject
                or bool(
                    requested_weekday
                )
                or has_date_word
            )
        ):
            intent = "SHOW_FOOD_MENU"

        if not intent:
            return result

        entities = dict(
            result.get("entities")
            or {}
        )

        inferred_date = (
            self._infer_menu_date(
                text,
                conversation_payload,
            )
        )

        candidate_dates = {
            str(
                item.get(
                    "day",
                    {},
                ).get("date")
                or ""
            ).strip()
            for item in food_candidates
            if isinstance(
                item,
                dict,
            )
            and str(
                item.get(
                    "day",
                    {},
                ).get("date")
                or ""
            ).strip()
        }

        if (
            not inferred_date
            and len(candidate_dates) == 1
        ):
            inferred_date = next(
                iter(candidate_dates)
            )

        if inferred_date:
            entities["date"] = str(
                inferred_date
            )

        state = dict(
            result.get("state")
            or {}
        )

        state.update(
            {
                "domain": "FOOD",
                "intent": intent,
                "entities": entities,
                "missingFields": [],
            }
        )

        return {
            **result,
            "domain": "FOOD",
            "intent": intent,
            "entities": entities,
            "confidence": 0.99,
            "missingFields": [],
            "needsClarification": False,
            "conversationComplete": False,
            "clarification": None,
            "errors": [],
            "state": state,
        }

'''

text = replace_once(
    text,
    helper_anchor,
    helper_code + helper_anchor,
    "food router helper",
)


# ==================================================
# 3. مخفی‌کردن آمار عمومی بی‌معنی
# ==================================================

public_percent_old = '''                if public_percent is not None:
                    details.append(
                        "رزرو عمومی: "
                        f"{int(public_percent)}٪ "
                        "از ظرفیت"
                    )
'''

public_percent_new = '''                if (
                    public_percent is not None
                    and int(public_percent) > 0
                ):
                    details.append(
                        "رزرو عمومی: "
                        f"{int(public_percent)}٪ "
                        "از ظرفیت"
                    )
'''

text = replace_once(
    text,
    public_percent_old,
    public_percent_new,
    "public percent display",
)


rating_old = '''                if average_rate is not None:
                    try:
'''

rating_new = '''                if (
                    average_rate is not None
                    and vote_count > 0
                ):
                    try:
'''

text = replace_once(
    text,
    rating_old,
    rating_new,
    "rating display",
)


public_favorite_old = '''                if food.get(
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
'''

public_favorite_new = '''                if (
                    food.get(
                        "isPublicFavorite"
                    )
                    and (
                        (
                            public_percent
                            is not None
                            and int(
                                public_percent
                            ) > 0
                        )
                        or vote_count > 0
                    )
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
                        "voteCount": (
                            vote_count
                        ),
                    }
'''

text = replace_once(
    text,
    public_favorite_old,
    public_favorite_new,
    "public favorite display",
)


summary_percent_old = '''            if (
                public_best[
                    "publicPercent"
                ]
                is not None
            ):
'''

summary_percent_new = '''            if (
                public_best[
                    "publicPercent"
                ]
                is not None
                and int(
                    public_best[
                        "publicPercent"
                    ]
                ) > 0
            ):
'''

text = replace_once(
    text,
    summary_percent_old,
    summary_percent_new,
    "public summary percent",
)


summary_rating_old = '''            if (
                public_best[
                    "averageRate"
                ]
                is not None
            ):
'''

summary_rating_new = '''            if (
                public_best[
                    "averageRate"
                ]
                is not None
                and int(
                    public_best.get(
                        "voteCount"
                    )
                    or 0
                ) > 0
            ):
'''

text = replace_once(
    text,
    summary_rating_old,
    summary_rating_new,
    "public summary rating",
)


# ==================================================
# 4. ذخیره، Compile و تست مسیر واقعی Router
# ==================================================

try:
    CHAT.write_text(
        text,
        encoding="utf-8",
    )

    py_compile.compile(
        str(CHAT),
        doraise=True,
    )

    sys.path.insert(
        0,
        str(ROOT),
    )

    importlib.invalidate_caches()

    module = importlib.import_module(
        "app.application.services.chat_service"
    )

    service_class = next(
        value
        for value in vars(
            module
        ).values()
        if isinstance(
            value,
            type,
        )
        and hasattr(
            value,
            "_override_explicit_food_command",
        )
        and hasattr(
            value,
            "_find_food_candidates",
        )
    )

    service = service_class.__new__(
        service_class
    )

    conversation = {
        "lastDomain": "FOOD",
        "recentMenus": [
            {
                "date": "1405/05/04",
                "dayOfWeek": "یکشنبه",
                "foods": [
                    {
                        "planDetailId": 1,
                        "foodName": (
                            "قیمه سیب زمینی"
                        ),
                    }
                ],
            },
            {
                "date": "1405/05/05",
                "dayOfWeek": "دوشنبه",
                "foods": [
                    {
                        "planDetailId": 2,
                        "foodName": (
                            "پلو یونانی"
                        ),
                    }
                ],
            },
            {
                "date": "1405/05/06",
                "dayOfWeek": "سه شنبه",
                "foods": [
                    {
                        "planDetailId": 3,
                        "foodName": (
                            "واویشکا"
                        ),
                    }
                ],
            },
        ],
    }

    tests = {
        "منوی غذای دوشنبه رو بده": (
            "SHOW_FOOD_MENU"
        ),
        "غذای امروز چیه": (
            "SHOW_FOOD_MENU"
        ),
        (
            "غذای یکشنبه "
            "4 مرداد رو نشون بده"
        ): (
            "SHOW_FOOD_MENU"
        ),
        (
            "برای سه شنبه "
            "واویشکا رزرو کن"
        ): (
            "RESERVE_FOOD"
        ),
        (
            "برای یکشنبه "
            "قیمه سیب زمینی "
            "رو ثبت کن"
        ): (
            "RESERVE_FOOD"
        ),
        (
            "پلو یونانی "
            "انتخاب شود"
        ): (
            "RESERVE_FOOD"
        ),
    }

    for phrase, expected in (
        tests.items()
    ):
        actual_result = (
            service
            ._override_explicit_food_command(
                {
                    "domain": "UNKNOWN",
                    "intent": "UNKNOWN",
                    "entities": {},
                    "needsClarification": True,
                    "missingFields": [
                        "intent"
                    ],
                },
                phrase,
                conversation,
            )
        )

        actual = actual_result.get(
            "intent"
        )

        if actual != expected:
            raise RuntimeError(
                "ROUTER_TEST_FAILED: "
                f"{phrase} "
                f"actual={actual} "
                f"expected={expected}"
            )

except Exception:
    shutil.copy2(
        BACKUP,
        CHAT,
    )
    raise


print("PATCH_OK")
print("ROUTER_TESTS_OK")
print(f"BACKUP={BACKUP}")