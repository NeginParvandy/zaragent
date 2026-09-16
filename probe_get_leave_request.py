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

    data = payload.get("data")

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for key in (
            "results",
            "items",
            "rows",
            "value",
        ):
            rows = data.get(key)

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


def build_pilot_context() -> AgentContext:
    config_path = (
        ROOT
        / "pilot_hr_override.json"
    )

    config = json.loads(
        config_path.read_text(
            encoding="utf-8-sig"
        )
    )

    if config.get("enabled") is not True:
        raise RuntimeError(
            "PILOT_OVERRIDE_IS_DISABLED"
        )

    employee_id = str(
        config.get(
            "employeeId",
            "",
        )
    ).strip()

    conversation_id = str(
        config.get(
            "conversationId",
            "pilot-05000602",
        )
        or "pilot-05000602"
    ).strip()

    if employee_id != "05000602":
        raise RuntimeError(
            "PILOT_EMPLOYEE_ID_MISMATCH"
        )

    authorization_token = str(
        config.get(
            "authorizationToken",
            "",
        )
    ).strip()

    username_hash = str(
        config.get(
            "usernameHash",
            "",
        )
    ).strip()

    password_hash = str(
        config.get(
            "passwordHash",
            "",
        )
    ).strip()

    digit_code = config.get(
        "digitCode"
    )

    if not all(
        (
            authorization_token,
            username_hash,
            password_hash,
            digit_code is not None,
        )
    ):
        raise RuntimeError(
            "PILOT_CREDENTIALS_INCOMPLETE"
        )

    return AgentContext(
        employee_id=employee_id,
        conversation_id=conversation_id,
        session=UserSession(
            authorization_token=authorization_token,
            username_hash=username_hash,
            password_hash=password_hash,
            digit_code=int(digit_code),
        ),
    )


async def main() -> None:
    if len(sys.argv) != 2:
        print(
            "USAGE: probe_get_leave_request.py "
            "START_DATE"
        )
        print(
            "EXAMPLE: "
            "probe_get_leave_request.py "
            "1405/05/01"
        )
        raise SystemExit(2)

    start_date = sys.argv[1].strip()

    settings = get_settings()
    context = build_pilot_context()

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

    safe_date = start_date.replace(
        "/",
        "-",
    )

    output_file = (
        output_dir
        / f"get_leave_request_{safe_date}.json"
    )

    try:
        response = await service.get_leave_requests(
            context,
            start_date,
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
            "RESPONSE_TYPE="
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