from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterable, Mapping


EMPTY_REPLY = "اطلاعات مانده مرخصی برای شما پیدا نشد."

_NO_ACTIVITY_REPLY = (
    "در حال حاضر مرخصی مصرف‌شده یا "
    "درخواست در انتظار ندارید."
)

_PERSIAN_TRANSLATION = str.maketrans(
    {
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ؤ": "و",
        "إ": "ا",
        "أ": "ا",
        "ۀ": "ه",
        "\u200c": " ",
        "\u200f": "",
        "\u200e": "",
        "\ufeff": "",
    }
)

_ENGLISH_TO_PERSIAN_DIGITS = str.maketrans(
    "0123456789",
    "۰۱۲۳۴۵۶۷۸۹",
)

_PERSIAN_TO_ENGLISH_DIGITS = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹",
    "0123456789",
)

_ARABIC_TO_ENGLISH_DIGITS = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩",
    "0123456789",
)


def format_leave_balance_reply(
    payload: Any,
) -> str:
    """
    Convert the HR time-account response into a clean Persian reply.

    This function only formats data and never mutates the original payload.
    Invalid rows are ignored safely.
    """

    rows = list(_extract_rows(payload))

    formatted_accounts: list[str] = []
    has_activity = False

    for row in rows:
        account = _format_account(row)

        if account is None:
            continue

        formatted_accounts.append(account["text"])

        if account["has_activity"]:
            has_activity = True

    if not formatted_accounts:
        return EMPTY_REPLY

    parts = [
        "مانده مرخصی شما:",
        "",
        "\n".join(formatted_accounts),
    ]

    if not has_activity:
        parts.extend(
            [
                "",
                _NO_ACTIVITY_REPLY,
            ]
        )

    return "\n".join(parts)


def _extract_rows(
    payload: Any,
) -> Iterable[Mapping[str, Any]]:
    if isinstance(payload, (list, tuple)):
        candidates = payload

    elif isinstance(payload, Mapping):
        candidates = None

        for key in (
            "data",
            "items",
            "result",
            "results",
            "timeAccounts",
            "timeAccount",
        ):
            value = payload.get(key)

            if isinstance(value, (list, tuple)):
                candidates = value
                break

        if candidates is None:
            return

    else:
        return

    for item in candidates:
        if isinstance(item, Mapping):
            yield item


def _format_account(
    row: Mapping[str, Any],
) -> dict[str, Any] | None:
    account_name = _normalize_account_name(
        row.get("timeAccountTypeName")
    )

    if not account_name:
        return None

    unit = _resolve_unit(row)

    available = _to_decimal(
        row.get("balanceAvailableQuantity")
    )
    used = _to_decimal(
        row.get("balanceUsedQuantity")
    )
    approved = _to_decimal(
        row.get("balanceApprovedQuantity")
    )
    requested = _to_decimal(
        row.get("balanceRequestedQuantity")
    )
    planned = _to_decimal(
        row.get("balancePlannedQuantity")
    )

    main_line = (
        f"• {account_name}: "
        f"{_format_number(available)} "
        f"{unit} قابل استفاده"
    )

    details: list[str] = []

    detail_values = (
        ("مصرف‌شده", used),
        ("تأییدشده", approved),
        ("در انتظار", requested),
        ("برنامه‌ریزی‌شده", planned),
    )

    for label, value in detail_values:
        if not _is_non_zero(value):
            continue

        details.append(
            f"{label}: {_format_number(value)} {unit}"
        )

    if details:
        text = (
            main_line
            + "\n  "
            + " | ".join(details)
        )
    else:
        text = main_line

    return {
        "text": text,
        "has_activity": bool(details),
    }


def _normalize_account_name(
    value: Any,
) -> str:
    if not isinstance(value, str):
        return ""

    text = value.translate(
        _PERSIAN_TRANSLATION
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    if not text:
        return ""

    known_names = {
        "مرخصی استحقاقی": "مرخصی استحقاقی",
        "مرخصی استعلاجی": "مرخصی استعلاجی",
        "مرخصی معذوریت فوت": "مرخصی معذوریت فوت",
    }

    return known_names.get(
        text,
        text,
    )


def _resolve_unit(
    row: Mapping[str, Any],
) -> str:
    raw_name = row.get("timeUnitName")
    raw_code = row.get("timeUnitCode")

    unit_name = (
        str(raw_name).strip().lower()
        if raw_name is not None
        else ""
    )

    unit_code = (
        str(raw_code).strip()
        if raw_code is not None
        else ""
    )

    hour_units = {
        "hour",
        "hours",
        "hr",
        "hrs",
        "ساعت",
    }

    day_units = {
        "day",
        "days",
        "روز",
    }

    if unit_name in hour_units:
        return "ساعت"

    if unit_name in day_units:
        return "روز"

    if unit_code == "001":
        return "ساعت"

    if unit_code == "002":
        return "روز"

    return "واحد"


def _to_decimal(
    value: Any,
) -> Decimal:
    if value is None or isinstance(value, bool):
        return Decimal("0")

    if isinstance(value, Decimal):
        return value

    text = str(value).strip()

    if not text:
        return Decimal("0")

    text = text.translate(
        _PERSIAN_TO_ENGLISH_DIGITS
    )
    text = text.translate(
        _ARABIC_TO_ENGLISH_DIGITS
    )

    text = (
        text.replace("٬", "")
        .replace(",", "")
        .replace("٫", ".")
    )

    try:
        return Decimal(text)

    except (
        InvalidOperation,
        ValueError,
        TypeError,
    ):
        return Decimal("0")


def _round_number(
    value: Decimal,
) -> Decimal:
    rounded = value.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    if rounded == Decimal("-0.00"):
        return Decimal("0")

    return rounded


def _is_non_zero(
    value: Decimal,
) -> bool:
    return _round_number(value) != Decimal("0")


def _format_number(
    value: Decimal,
) -> str:
    rounded = _round_number(value)

    if rounded == rounded.to_integral_value():
        english = f"{int(rounded):,}"

    else:
        english = format(
            rounded,
            "f",
        ).rstrip("0").rstrip(".")

        integer_part, decimal_part = english.split(
            ".",
            maxsplit=1,
        )

        try:
            integer_part = f"{int(integer_part):,}"
        except ValueError:
            pass

        english = (
            f"{integer_part}.{decimal_part}"
        )

    persian = english.translate(
        _ENGLISH_TO_PERSIAN_DIGITS
    )

    return (
        persian.replace(",", "٬")
        .replace(".", "٫")
    )


__all__ = [
    "format_leave_balance_reply",
]