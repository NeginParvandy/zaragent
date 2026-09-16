from pathlib import Path
import py_compile
import re
import shutil


CHAT = Path(
    r"D:\serviceAi\app\application"
    r"\services\chat_service.py"
)

BACKUP = CHAT.with_name(
    CHAT.name
    + ".bak_before_food_weekly_menu_v2"
)

MARKER = "FOOD_WEEKLY_MENU_V2"


def fail(message: str) -> None:
    raise RuntimeError(message)


text = CHAT.read_text(
    encoding="utf-8-sig"
)

if MARKER in text:
    print("ALREADY_PATCHED")
    raise SystemExit(0)


if not BACKUP.exists():
    shutil.copy2(
        CHAT,
        BACKUP,
    )


# --------------------------------------------------
# 1. Ignore stale activeDate for a general menu query
# --------------------------------------------------

target_pattern = re.compile(
    r"(?P<target>"
    r"        target_date = \(\n"
    r"            dates\[0\]\n"
    r"            if dates\n"
    r"            else None\n"
    r"        \)\n"
    r")"
)

target_match = target_pattern.search(text)

if target_match is None:
    fail(
        "ANCHOR_NOT_FOUND: target_date"
    )


weekly_logic = '''
        # FOOD_WEEKLY_MENU_V2
        normalized_food_text = (
            normalize_nlu_text(text)
        )

        menu_request_words = [
            "منو",
            "نشان بده",
            "نشون بده",
            "نشون",
            "نمایش",
            "لیست",
            "ببین",
            "بیار",
            "چه غذایی",
            "غذاها",
        ]

        reservation_request_words = [
            "رزرو",
            "ثبت",
            "انتخاب",
            "برام بگیر",
            "برایم بگیر",
            "بگیرش",
            "سفارش",
        ]

        relative_date_words = [
            "امروز",
            "فردا",
            "پس فردا",
            "پسفردا",
        ]

        has_explicit_numeric_date = bool(
            re.search(
                r"(?:13|14)[0-9]{2}"
                r"\\s*/\\s*[0-9]{1,2}"
                r"\\s*/\\s*[0-9]{1,2}",
                normalized_food_text,
            )
        )

        has_explicit_named_date = bool(
            re.search(
                r"[0-9۰-۹]{1,2}\\s*"
                r"(?:فروردین|اردیبهشت|خرداد|"
                r"تیر|مرداد|شهریور|مهر|آبان|"
                r"آذر|دی|بهمن|اسفند)",
                normalized_food_text,
            )
        )

        has_relative_date = any(
            word in normalized_food_text
            for word in relative_date_words
        )

        is_menu_request = any(
            word in normalized_food_text
            for word in menu_request_words
        )

        is_reservation_request = any(
            word in normalized_food_text
            for word in reservation_request_words
        )

        broad_weekly_menu_request = (
            is_menu_request
            and not is_reservation_request
            and not requested_weekday
            and not has_explicit_numeric_date
            and not has_explicit_named_date
            and not has_relative_date
        )

        weekday_without_explicit_date = (
            bool(requested_weekday)
            and not has_explicit_numeric_date
            and not has_explicit_named_date
            and not has_relative_date
        )

        if (
            broad_weekly_menu_request
            or weekday_without_explicit_date
        ):
            target_date = None
'''

text = (
    text[:target_match.end()]
    + weekly_logic
    + text[target_match.end():]
)


# --------------------------------------------------
# 2. Weekly menu display:
#    - all unreserved days
#    - reserved day marker
#    - hide foods with no remaining capacity
# --------------------------------------------------

menu_pattern = re.compile(
    r"    @staticmethod\n"
    r"    def _menu_reply\(\n"
    r".*?"
    r"(?=\n    @staticmethod\n"
    r"    def _reservation_status_reply\()",
    re.DOTALL,
)

menu_match = menu_pattern.search(text)

if menu_match is None:
    fail(
        "ANCHOR_NOT_FOUND: _menu_reply"
    )


new_menu_reply = '''    @staticmethod
    def _menu_reply(
        days: list[dict[str, Any]],
    ) -> str:
        if not days:
            return (
                "برای تاریخ موردنظر منویی "
                "پیدا نشد."
            )

        lines: list[str] = [
            (
                "منوی این هفته:"
                if len(days) > 1
                else "منوی غذا:"
            )
        ]

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
                and date_value not in day_label
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
                    "✅ قبلاً رزرو کرده‌اید: "
                    + (
                        selected_name
                        or "غذای رزروشده"
                    )
                )
                continue

            available_names: list[str] = []

            for food in foods:
                food_name = str(
                    food.get("foodName")
                    or ""
                ).strip()

                if not food_name:
                    continue

                remain_count = parse_int(
                    food.get("remainCount")
                )

                if (
                    remain_count is not None
                    and remain_count <= 0
                ):
                    continue

                available_names.append(
                    food_name
                )

            if available_names:
                lines.extend(
                    f"• {food_name}"
                    for food_name
                    in available_names
                )
            else:
                lines.append(
                    "• غذای قابل رزروی "
                    "اعلام نشده است."
                )

        return "\\n".join(lines)
'''


text = (
    text[:menu_match.start()]
    + new_menu_reply
    + text[menu_match.end():]
)


try:
    CHAT.write_text(
        text,
        encoding="utf-8",
    )

    py_compile.compile(
        str(CHAT),
        doraise=True,
    )

except Exception:
    shutil.copy2(
        BACKUP,
        CHAT,
    )
    raise


print("PATCH_OK")
print(f"BACKUP={BACKUP}")