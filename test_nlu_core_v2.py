from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any


ROOT_DIR = Path(r"D:\serviceAi")

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from app.application.services.nlu_core import (
    analyze_message,
)


REFERENCE_DATE = "1405/04/20"


class NluCoreV2Tests(unittest.TestCase):
    def analyze(
        self,
        message: str,
        *,
        state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = analyze_message(
            message,
            reference_date=REFERENCE_DATE,
            conversation_state=state,
        )

        self.assertIsInstance(result, dict)
        self.assertIn("domain", result)
        self.assertIn("intent", result)
        self.assertIn("entities", result)
        self.assertIn("confidence", result)
        self.assertIn("missingFields", result)
        self.assertIn("needsClarification", result)
        self.assertIn("conversationComplete", result)
        self.assertIn("state", result)

        self.assertIsInstance(
            result["entities"],
            dict,
        )
        self.assertIsInstance(
            result["missingFields"],
            list,
        )
        self.assertIsInstance(
            result["state"],
            dict,
        )

        return result

    def assert_intent(
        self,
        message: str,
        domain: str,
        intent: str,
    ) -> dict[str, Any]:
        result = self.analyze(message)

        self.assertEqual(
            result["domain"],
            domain,
        )
        self.assertEqual(
            result["intent"],
            intent,
        )
        self.assertGreaterEqual(
            result["confidence"],
            0.70,
        )

        return result

    # ---------------------------------------------------------
    # Food
    # ---------------------------------------------------------

    def test_food_reservation_short_phrase(self) -> None:
        result = self.assert_intent(
            "رزرو غذا",
            "FOOD",
            "RESERVE_FOOD",
        )

        self.assertFalse(
            result["conversationComplete"]
        )
        self.assertTrue(
            result["needsClarification"]
        )
        self.assertIn(
            "date",
            result["missingFields"],
        )

    def test_food_reservation_natural_variants(self) -> None:
        messages = [
            "برام غذا رزرو کن",
            "ناهار فردا رو بگیر",
            "غذای فردا را ثبت کن",
            "برای فردا غذا میخوام",
            "ناهار این هفته رو رزرو کن",
            "غذای هفته رو برام بگیر",
        ]

        for message in messages:
            with self.subTest(message=message):
                result = self.analyze(message)

                self.assertEqual(
                    result["domain"],
                    "FOOD",
                )
                self.assertEqual(
                    result["intent"],
                    "RESERVE_FOOD",
                )

    def test_food_menu_intent(self) -> None:
        messages = [
            "منوی غذا رو نشون بده",
            "فردا چه غذایی داریم",
            "ناهارهای این هفته چیه",
        ]

        for message in messages:
            with self.subTest(message=message):
                result = self.analyze(message)

                self.assertEqual(
                    result["domain"],
                    "FOOD",
                )
                self.assertEqual(
                    result["intent"],
                    "SHOW_FOOD_MENU",
                )

    def test_food_reservation_status(self) -> None:
        result = self.assert_intent(
            "برای فردا چی رزرو کردم؟",
            "FOOD",
            "SHOW_FOOD_RESERVATION",
        )

        self.assertEqual(
            result["entities"].get("date"),
            "1405/04/21",
        )

    def test_food_cancel_intent(self) -> None:
        messages = [
            "رزرو غذای فردا رو لغو کن",
            "غذای رزرو شده فردا رو کنسل کن",
            "رزرو ناهارم رو حذف کن",
        ]

        for message in messages:
            with self.subTest(message=message):
                result = self.analyze(message)

                self.assertEqual(
                    result["domain"],
                    "FOOD",
                )
                self.assertEqual(
                    result["intent"],
                    "CANCEL_FOOD",
                )

    def test_thanks_is_not_food_menu(self) -> None:
        messages = [
            "نه ممنون",
            "خیلی ممنون",
            "ممنونم",
        ]

        for message in messages:
            with self.subTest(message=message):
                result = self.analyze(message)

                self.assertNotEqual(
                    result["intent"],
                    "SHOW_FOOD_MENU",
                )

    # ---------------------------------------------------------
    # Leave and mission
    # ---------------------------------------------------------

    def test_leave_balance_variants(self) -> None:
        messages = [
            "مانده مرخصی من چقدره",
            "چقدر مرخصی دارم",
            "مرخصی باقی مونده ام رو بگو",
            "چند ساعت مرخصی برام مونده",
            "وضعیت حساب مرخصی من",
        ]

        for message in messages:
            with self.subTest(message=message):
                result = self.analyze(message)

                self.assertEqual(
                    result["domain"],
                    "LEAVE",
                )
                self.assertEqual(
                    result["intent"],
                    "GET_LEAVE_BALANCE",
                )
                self.assertTrue(
                    result["conversationComplete"]
                )
                self.assertFalse(
                    result["needsClarification"]
                )

    def test_create_leave_for_tomorrow(self) -> None:
        result = self.assert_intent(
            "میخوام برای فردا مرخصی ثبت کنم",
            "LEAVE",
            "CREATE_LEAVE",
        )

        self.assertEqual(
            result["entities"].get("startDate"),
            "1405/04/21",
        )
        self.assertEqual(
            result["entities"].get("endDate"),
            "1405/04/21",
        )

    def test_create_mission(self) -> None:
        result = self.assert_intent(
            "برای پس فردا مأموریت ثبت کن",
            "MISSION",
            "CREATE_MISSION",
        )

        self.assertEqual(
            result["entities"].get("startDate"),
            "1405/04/22",
        )

    # ---------------------------------------------------------
    # Relative and explicit dates
    # ---------------------------------------------------------

    def test_relative_dates(self) -> None:
        cases = {
            "امروز": "1405/04/20",
            "فردا": "1405/04/21",
            "پس فردا": "1405/04/22",
            "پس‌فردا": "1405/04/22",
            "دیروز": "1405/04/19",
        }

        for phrase, expected_date in cases.items():
            with self.subTest(phrase=phrase):
                result = self.analyze(
                    f"تردد {phrase} را نشان بده"
                )

                self.assertEqual(
                    result["entities"].get("date"),
                    expected_date,
                )

    def test_explicit_jalali_date(self) -> None:
        messages = [
            "برای 1405/04/25 مرخصی ثبت کن",
            "برای ۱۴۰۵/۰۴/۲۵ مرخصی ثبت کن",
            "برای 1405-04-25 مرخصی ثبت کن",
        ]

        for message in messages:
            with self.subTest(message=message):
                result = self.analyze(message)

                self.assertEqual(
                    result["entities"].get("startDate"),
                    "1405/04/25",
                )

    # ---------------------------------------------------------
    # Attendance and time parsing
    # ---------------------------------------------------------

    def test_attendance_entry_tomorrow_8_am(self) -> None:
        result = self.assert_intent(
            "ثبت تردد برای فردا ساعت 8 صبح",
            "ATTENDANCE",
            "CREATE_TIME_EVENT",
        )

        self.assertEqual(
            result["entities"].get("date"),
            "1405/04/21",
        )
        self.assertEqual(
            result["entities"].get("time"),
            "08:00",
        )

    def test_attendance_entry_keyword(self) -> None:
        result = self.analyze(
            "فردا ساعت هشت صبح ورود بزن"
        )

        self.assertEqual(
            result["domain"],
            "ATTENDANCE",
        )
        self.assertEqual(
            result["intent"],
            "CREATE_TIME_EVENT",
        )
        self.assertEqual(
            result["entities"].get("eventType"),
            "ENTRY",
        )

    def test_attendance_exit_keyword(self) -> None:
        result = self.analyze(
            "فردا ساعت ده شب خروج ثبت کن"
        )

        self.assertEqual(
            result["entities"].get("time"),
            "22:00",
        )
        self.assertEqual(
            result["entities"].get("eventType"),
            "EXIT",
        )

    def test_numeric_time_with_minutes(self) -> None:
        messages = [
            "فردا ساعت 10:50 ورود ثبت کن",
            "فردا ساعت ۱۰:۵۰ ورود ثبت کن",
            "فردا ساعت 10 و 50 دقیقه ورود ثبت کن",
            "فردا ساعت ۱۰ و ۵۰ دقیقه ورود ثبت کن",
        ]

        for message in messages:
            with self.subTest(message=message):
                result = self.analyze(message)

                self.assertEqual(
                    result["entities"].get("time"),
                    "10:50",
                )

    def test_word_time_with_minutes(self) -> None:
        messages = [
            "فردا ساعت ده و پنجاه دقیقه ورود ثبت کن",
            "فردا ساعت دهو پنجاه دقیقه ورود ثبت کن",
            "فردا ساعت ده و پنجاه ورود بزن",
        ]

        for message in messages:
            with self.subTest(message=message):
                result = self.analyze(message)

                self.assertEqual(
                    result["entities"].get("time"),
                    "10:50",
                )

    def test_time_with_half_and_quarter(self) -> None:
        cases = {
            "ساعت هشت و نیم صبح": "08:30",
            "ساعت هشت و ربع صبح": "08:15",
            "ساعت نه و سه ربع شب": "21:45",
        }

        for phrase, expected_time in cases.items():
            with self.subTest(phrase=phrase):
                result = self.analyze(
                    f"فردا {phrase} تردد ثبت کن"
                )

                self.assertEqual(
                    result["entities"].get("time"),
                    expected_time,
                )

    def test_pm_time_conversion(self) -> None:
        cases = {
            "ده شب": "22:00",
            "ده و پنجاه دقیقه شب": "22:50",
            "هشت عصر": "20:00",
            "یک ظهر": "13:00",
        }

        for phrase, expected_time in cases.items():
            with self.subTest(phrase=phrase):
                result = self.analyze(
                    f"فردا ساعت {phrase} خروج ثبت کن"
                )

                self.assertEqual(
                    result["entities"].get("time"),
                    expected_time,
                )

    def test_attendance_time_range(self) -> None:
        result = self.analyze(
            (
                "برای فردا از ساعت هشت و ده دقیقه صبح "
                "تا ده و پنجاه دقیقه شب تردد ثبت کن"
            )
        )

        self.assertEqual(
            result["domain"],
            "ATTENDANCE",
        )
        self.assertEqual(
            result["intent"],
            "CREATE_TIME_EVENT_RANGE",
        )
        self.assertEqual(
            result["entities"].get("date"),
            "1405/04/21",
        )
        self.assertEqual(
            result["entities"].get("startTime"),
            "08:10",
        )
        self.assertEqual(
            result["entities"].get("endTime"),
            "22:50",
        )

    def test_ambiguous_time_requests_clarification(
        self,
    ) -> None:
        result = self.analyze(
            "فردا ساعت 10 تردد ثبت کن"
        )

        self.assertTrue(
            result["needsClarification"]
        )
        self.assertFalse(
            result["conversationComplete"]
        )
        self.assertIn(
            "meridiem",
            result["missingFields"],
        )

        clarification = str(
            result.get("clarification") or ""
        )

        self.assertTrue(
            "صبح" in clarification
            and "شب" in clarification
        )

    def test_invalid_minute_is_not_accepted(self) -> None:
        result = self.analyze(
            "فردا ساعت ده و هفتاد و پنج دقیقه ورود ثبت کن"
        )

        self.assertTrue(
            result["needsClarification"]
        )
        self.assertFalse(
            result["conversationComplete"]
        )

        errors = result.get("errors") or []

        self.assertTrue(errors)

    # ---------------------------------------------------------
    # Multi-turn conversation and slot filling
    # ---------------------------------------------------------

    def test_conversation_continues_for_missing_date(
        self,
    ) -> None:
        first = self.analyze(
            "رزرو غذا"
        )

        self.assertIn(
            "date",
            first["missingFields"],
        )

        second = self.analyze(
            "برای فردا",
            state=first["state"],
        )

        self.assertEqual(
            second["domain"],
            "FOOD",
        )
        self.assertEqual(
            second["intent"],
            "RESERVE_FOOD",
        )
        self.assertEqual(
            second["entities"].get("date"),
            "1405/04/21",
        )
        self.assertNotIn(
            "date",
            second["missingFields"],
        )

    def test_conversation_continues_for_missing_time(
        self,
    ) -> None:
        first = self.analyze(
            "برای فردا تردد ثبت کن"
        )

        self.assertIn(
            "time",
            first["missingFields"],
        )

        second = self.analyze(
            "ساعت ده و پنجاه دقیقه صبح",
            state=first["state"],
        )

        self.assertEqual(
            second["domain"],
            "ATTENDANCE",
        )
        self.assertEqual(
            second["intent"],
            "CREATE_TIME_EVENT",
        )
        self.assertEqual(
            second["entities"].get("date"),
            "1405/04/21",
        )
        self.assertEqual(
            second["entities"].get("time"),
            "10:50",
        )

    def test_user_can_correct_previous_time(self) -> None:
        first = self.analyze(
            "فردا ساعت ده صبح ورود ثبت کن"
        )

        second = self.analyze(
            "نه، ساعت ده و پنجاه دقیقه شب",
            state=first["state"],
        )

        self.assertEqual(
            second["entities"].get("time"),
            "22:50",
        )

    def test_confirmation_reply_keeps_context(self) -> None:
        first = self.analyze(
            "برای فردا غذا رزرو کن"
        )

        second = self.analyze(
            "بله",
            state=first["state"],
        )

        self.assertEqual(
            second["intent"],
            "CONFIRM",
        )
        self.assertEqual(
            second["entities"].get(
                "parentIntent"
            ),
            "RESERVE_FOOD",
        )

    def test_cancel_reply_ends_conversation(self) -> None:
        first = self.analyze(
            "برای فردا مرخصی ثبت کن"
        )

        second = self.analyze(
            "بیخیال، لغو کن",
            state=first["state"],
        )

        self.assertEqual(
            second["intent"],
            "CANCEL_CONVERSATION",
        )
        self.assertTrue(
            second["conversationComplete"]
        )
        self.assertEqual(
            second["state"],
            {},
        )

    # ---------------------------------------------------------
    # Guidance, unsupported and out-of-scope
    # ---------------------------------------------------------

    def test_incomplete_request_has_useful_guidance(
        self,
    ) -> None:
        result = self.analyze(
            "ثبت کن"
        )

        self.assertTrue(
            result["needsClarification"]
        )

        clarification = str(
            result.get("clarification") or ""
        )

        self.assertTrue(
            "غذا" in clarification
            or "مرخصی" in clarification
            or "تردد" in clarification
        )

    def test_out_of_scope_request(self) -> None:
        result = self.analyze(
            "قیمت دلار امروز چنده"
        )

        self.assertEqual(
            result["domain"],
            "OUT_OF_SCOPE",
        )
        self.assertEqual(
            result["intent"],
            "UNSUPPORTED",
        )
        self.assertTrue(
            result["conversationComplete"]
        )

    def test_empty_message_is_guided(self) -> None:
        result = self.analyze("   ")

        self.assertEqual(
            result["intent"],
            "EMPTY_MESSAGE",
        )
        self.assertTrue(
            result["needsClarification"]
        )

    # ---------------------------------------------------------
    # Response safety and consistency
    # ---------------------------------------------------------

    def test_result_never_returns_list_as_state_or_entities(
        self,
    ) -> None:
        messages = [
            "رزرو غذا",
            "مانده مرخصی من",
            "فردا ساعت هشت صبح ورود ثبت کن",
            "قیمت دلار چنده",
        ]

        for message in messages:
            with self.subTest(message=message):
                result = self.analyze(message)

                self.assertIsInstance(
                    result["entities"],
                    dict,
                )
                self.assertIsInstance(
                    result["state"],
                    dict,
                )

    def test_normalization_handles_arabic_characters(
        self,
    ) -> None:
        result = self.analyze(
            "مانده مرخصي من چقدره"
        )

        self.assertEqual(
            result["domain"],
            "LEAVE",
        )
        self.assertEqual(
            result["intent"],
            "GET_LEAVE_BALANCE",
        )

    def test_normalization_handles_spacing_and_typo_style(
        self,
    ) -> None:
        messages = [
            "رزرو  غذا",
            "رزروغذا",
            "میخوام غذا رزروکنم",
            "ميخوام غذا رزرو كنم",
        ]

        for message in messages:
            with self.subTest(message=message):
                result = self.analyze(message)

                self.assertEqual(
                    result["domain"],
                    "FOOD",
                )
                self.assertEqual(
                    result["intent"],
                    "RESERVE_FOOD",
                )


if __name__ == "__main__":
    unittest.main(
        verbosity=2,
    )