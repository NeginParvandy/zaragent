from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any


ROOT_DIR = Path(r"D:\serviceAi")

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from app.application.services.leave_balance_formatter import (
    format_leave_balance_reply,
)


class LeaveBalanceFormatterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.real_api_rows: list[dict[str, Any]] = [
            {
                "employeeID": "05000602",
                "filterStartDate": "/Date(1784592000000)/",
                "processingStartDate": "/Date(1742515200000)/",
                "processingEndDate": "/Date(1773964800000)/",
                "timeAccountTypeCode": "10",
                "timeAccountTypeName": "مرخصي استحقاقي",
                "deductionStartDate": "/Date(1742515200000)/",
                "deductionEndDate": "/Date(1805500800000)/",
                "timeUnitCode": "001",
                "timeUnitName": "Hours",
                "balanceEntitlementQuantity": 100,
                "balanceUsedQuantity": 0,
                "balanceAvailableQuantity": 100,
                "balanceApprovedQuantity": 0,
                "balanceRequestedQuantity": 0,
                "balancePlannedQuantity": 0,
                "seqNo": "001",
            },
            {
                "employeeID": "05000602",
                "filterStartDate": "/Date(1784592000000)/",
                "processingStartDate": "/Date(1742515200000)/",
                "processingEndDate": "/Date(1773964800000)/",
                "timeAccountTypeCode": "20",
                "timeAccountTypeName": "مرخصي استعلاجي",
                "deductionStartDate": "/Date(1742515200000)/",
                "deductionEndDate": "/Date(1805500800000)/",
                "timeUnitCode": "001",
                "timeUnitName": "Hours",
                "balanceEntitlementQuantity": 100,
                "balanceUsedQuantity": 0,
                "balanceAvailableQuantity": 100,
                "balanceApprovedQuantity": 0,
                "balanceRequestedQuantity": 0,
                "balancePlannedQuantity": 0,
                "seqNo": "003",
            },
            {
                "employeeID": "05000602",
                "filterStartDate": "/Date(1784592000000)/",
                "processingStartDate": "/Date(1742515200000)/",
                "processingEndDate": "/Date(1773964800000)/",
                "timeAccountTypeCode": "30",
                "timeAccountTypeName": "مرخصي معذوريت فوت",
                "deductionStartDate": "/Date(1742515200000)/",
                "deductionEndDate": "/Date(1805500800000)/",
                "timeUnitCode": "001",
                "timeUnitName": "Hours",
                "balanceEntitlementQuantity": 100,
                "balanceUsedQuantity": 0,
                "balanceAvailableQuantity": 100,
                "balanceApprovedQuantity": 0,
                "balanceRequestedQuantity": 0,
                "balancePlannedQuantity": 0,
                "seqNo": "004",
            },
        ]

    def test_formats_real_hr_response_cleanly(self) -> None:
        reply = format_leave_balance_reply(
            self.real_api_rows
        )

        expected = (
            "مانده مرخصی شما:\n\n"
            "• مرخصی استحقاقی: ۱۰۰ ساعت قابل استفاده\n"
            "• مرخصی استعلاجی: ۱۰۰ ساعت قابل استفاده\n"
            "• مرخصی معذوریت فوت: ۱۰۰ ساعت قابل استفاده\n\n"
            "در حال حاضر مرخصی مصرف‌شده یا "
            "درخواست در انتظار ندارید."
        )

        self.assertEqual(reply, expected)

    def test_displays_non_zero_account_details(self) -> None:
        rows = [
            {
                "timeAccountTypeName": "مرخصي استحقاقي",
                "timeUnitName": "Hours",
                "balanceAvailableQuantity": 12.5,
                "balanceUsedQuantity": 4,
                "balanceApprovedQuantity": 1,
                "balanceRequestedQuantity": 2,
                "balancePlannedQuantity": 0.5,
            }
        ]

        reply = format_leave_balance_reply(rows)

        self.assertIn(
            "• مرخصی استحقاقی: "
            "۱۲٫۵ ساعت قابل استفاده",
            reply,
        )
        self.assertIn(
            "مصرف‌شده: ۴ ساعت",
            reply,
        )
        self.assertIn(
            "تأییدشده: ۱ ساعت",
            reply,
        )
        self.assertIn(
            "در انتظار: ۲ ساعت",
            reply,
        )
        self.assertIn(
            "برنامه‌ریزی‌شده: ۰٫۵ ساعت",
            reply,
        )

    def test_supports_day_unit(self) -> None:
        rows = [
            {
                "timeAccountTypeName": "مرخصی استحقاقی",
                "timeUnitName": "Days",
                "balanceAvailableQuantity": 2.25,
                "balanceUsedQuantity": 0,
                "balanceApprovedQuantity": 0,
                "balanceRequestedQuantity": 0,
                "balancePlannedQuantity": 0,
            }
        ]

        reply = format_leave_balance_reply(rows)

        self.assertIn(
            "۲٫۲۵ روز قابل استفاده",
            reply,
        )

    def test_handles_empty_response(self) -> None:
        for value in (
            None,
            [],
            {},
            "invalid",
        ):
            with self.subTest(value=value):
                reply = format_leave_balance_reply(
                    value
                )

                self.assertEqual(
                    reply,
                    (
                        "اطلاعات مانده مرخصی "
                        "برای شما پیدا نشد."
                    ),
                )

    def test_ignores_invalid_rows_without_crashing(self) -> None:
        rows = [
            None,
            "invalid",
            123,
            {},
            {
                "timeAccountTypeName": "",
                "balanceAvailableQuantity": 100,
            },
        ]

        reply = format_leave_balance_reply(rows)

        self.assertEqual(
            reply,
            (
                "اطلاعات مانده مرخصی "
                "برای شما پیدا نشد."
            ),
        )

    def test_does_not_expose_internal_fields(self) -> None:
        reply = format_leave_balance_reply(
            self.real_api_rows
        )

        forbidden_values = [
            "05000602",
            "employeeID",
            "timeAccountTypeCode",
            "seqNo",
            "/Date(",
            "1784592000000",
            "1742515200000",
            "1805500800000",
        ]

        for value in forbidden_values:
            with self.subTest(value=value):
                self.assertNotIn(value, reply)

    def test_formats_decimal_numbers_without_float_noise(
        self,
    ) -> None:
        rows = [
            {
                "timeAccountTypeName": "مرخصی استحقاقی",
                "timeUnitName": "Hours",
                "balanceAvailableQuantity": 8.333333333,
                "balanceUsedQuantity": 0,
                "balanceApprovedQuantity": 0,
                "balanceRequestedQuantity": 0,
                "balancePlannedQuantity": 0,
            }
        ]

        reply = format_leave_balance_reply(rows)

        self.assertIn(
            "۸٫۳۳ ساعت قابل استفاده",
            reply,
        )
        self.assertNotIn(
            "۸٫۳۳۳۳۳۳۳۳۳",
            reply,
        )


if __name__ == "__main__":
    unittest.main(
        verbosity=2,
    )