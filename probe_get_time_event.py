from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(r"D:\serviceAi")

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.application.services.hr_service import HrService
from app.core.config import get_settings
from app.domain.models import AgentContext, UserSession
from app.infrastructure.clients.personnel_client import PersonnelClient


SENSITIVE_KEY_PARTS = (
    "password",
    "username",
    "token",
    "authorization",
    "digitcode",
    "hash",
    "secret",
)


def is_sensitive_key(key: object) -> bool:
    normalized = (
        str(key)
        .replace("_", "")
        .replace("-", "")
        .lower()
    )

    return any(
        part in normalized
        for part in SENSITIVE_KEY_PARTS
    )


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}

        for key, item in value.items():
            if is_sensitive_key(key):
                result[str(key)] = "***REDACTED***"
            else:
                result[str(key)] = sanitize(item)

        return result

    if isinstance(value, list):
        return [
            sanitize(item)
            for item in value
        ]

    return value


def find_rows(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    direct_data = payload.get("data")

    if isinstance(direct_data, list):
        return direct_data

    if isinstance(direct_data, dict):
        for key in (
            "results",
            "items",
            "rows",
            "value",
        ):
            rows = direct_data.get(key)

            if isinstance(rows, list):
                return rows

    for key in (
        "results",
        "items",
        "rows",
        "value",
    ):
        rows = payload.get(key)

        if isinstance(rows, list):
            return rows

    return []


async def main() -> None:
    if len(sys.argv) != 3:
        print(
            "USAGE: probe_get_time_event.py "
            "START_DATE END_DATE"
        )
        print(
            "EXAMPLE: "
            "probe_get_time_event.py "
            "1405/05/01 1405/05/07"
        )
        raise SystemExit(2)

    start_date = sys.argv[1].strip()
    end_date = sys.argv[2].strip()

    settings = get_settings()

    # PROBE_PILOT_SESSION_V2
    # اطلاعات پایلوت فقط در حافظه بارگذاری می‌شوند.
    # هیچ Credentialی چاپ یا داخل فایل خروجی ذخیره نمی‌شود.
    pilot_config_path = (
        ROOT
        / "pilot_hr_override.json"
    )

    pilot_config = json.loads(
        pilot_config_path.read_text(
            encoding="utf-8-sig"
        )
    )

    if pilot_config.get("enabled") is not True:
        raise RuntimeError(
            "PILOT_OVERRIDE_IS_DISABLED"
        )

    pilot_employee_id = str(
        pilot_config.get(
            "employeeId",
            "",
        )
    ).strip()

    pilot_conversation_id = str(
        pilot_config.get(
            "conversationId",
            "pilot-05000602",
        )
        or "pilot-05000602"
    ).strip()

    if pilot_employee_id != "05000602":
        raise RuntimeError(
            "PILOT_EMPLOYEE_ID_MISMATCH"
        )

    if (
        pilot_conversation_id
        != "pilot-05000602"
    ):
        raise RuntimeError(
            "PILOT_CONVERSATION_ID_MISMATCH"
        )

    authorization_token = str(
        pilot_config.get(
            "authorizationToken",
            "",
        )
    ).strip()

    username_hash = str(
        pilot_config.get(
            "usernameHash",
            "",
        )
    ).strip()

    password_hash = str(
        pilot_config.get(
            "passwordHash",
            "",
        )
    ).strip()

    digit_code = pilot_config.get(
        "digitCode"
    )

    if not authorization_token:
        raise RuntimeError(
            "PILOT_AUTH_TOKEN_MISSING"
        )

    if not username_hash:
        raise RuntimeError(
            "PILOT_USERNAME_HASH_MISSING"
        )

    if not password_hash:
        raise RuntimeError(
            "PILOT_PASSWORD_HASH_MISSING"
        )

    if digit_code is None:
        raise RuntimeError(
            "PILOT_DIGIT_CODE_MISSING"
        )

    session = UserSession(
        authorization_token=authorization_token,
        username_hash=username_hash,
        password_hash=password_hash,
        digit_code=int(digit_code),
    )

    context = AgentContext(
        employee_id=pilot_employee_id,
        conversation_id=pilot_conversation_id,
        session=session,
    )

    client = PersonnelClient(settings)
    service = HrService(client)

    output_dir = (
        ROOT
        / "probe_outputs"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    safe_start = start_date.replace("/", "-")
    safe_end = end_date.replace("/", "-")

    output_file = (
        output_dir
        / (
            "get_time_event_"
            f"{safe_start}_"
            f"{safe_end}.json"
        )
    )

    try:
        response = await service.get_time_events(
            context,
            start_date,
            end_date,
        )

        sanitized = sanitize(response)
        rows = find_rows(sanitized)

        output_file.write_text(
            json.dumps(
                sanitized,
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

        print("PROBE_OK")
        print(
            f"RESPONSE_TYPE="
            f"{type(sanitized).__name__}"
        )

        if isinstance(sanitized, dict):
            print(
                "TOP_LEVEL_KEYS="
                + ",".join(
                    str(key)
                    for key in sanitized.keys()
                )
            )

        print(f"ROW_COUNT={len(rows)}")

        if rows and isinstance(rows[0], dict):
            print(
                "FIRST_ROW_KEYS="
                + ",".join(
                    str(key)
                    for key in rows[0].keys()
                )
            )

        print(f"OUTPUT={output_file}")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())