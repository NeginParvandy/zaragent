from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings


REQUEST_FILE = Path(r"D:\serviceAi\request_test.json")


def load_request() -> dict[str, Any]:
    return json.loads(
        REQUEST_FILE.read_text(encoding="utf-8-sig")
    )


def decode_token_payload(token: str) -> dict[str, Any]:
    token_value = token.strip()

    if token_value.lower().startswith("bearer "):
        token_value = token_value[7:].strip()

    parts = token_value.split(".")
    if len(parts) != 3:
        raise ValueError(
            "authorizationToken must be a complete JWT with two dots."
        )

    payload = parts[1]
    payload += "=" * ((4 - len(payload) % 4) % 4)

    return json.loads(
        base64.urlsafe_b64decode(
            payload.encode("ascii")
        ).decode("utf-8")
    )


def require_text(
    data: dict[str, Any],
    key: str,
) -> str:
    value = str(data.get(key) or "").strip()

    if not value or value == "string":
        raise ValueError(
            f"{key} is empty or still contains the Swagger placeholder."
        )

    return value


def print_response(
    label: str,
    response: httpx.Response,
) -> None:
    print(f"\n{label}")
    print(f"STATUS={response.status_code}")

    try:
        payload = response.json()
    except ValueError:
        print("JSON_RESPONSE=False")
        print(
            "BODY_PREFIX="
            + (response.text or "")[:200]
        )
        return

    if isinstance(payload, dict):
        print(f"HAS_ERROR={payload.get('hasError')}")
        print(f"MESSAGE={payload.get('message')}")
        print(
            "DATA_TYPE="
            + type(payload.get("data")).__name__
        )
    else:
        print(
            "JSON_TYPE="
            + type(payload).__name__
        )


def main() -> None:
    request_data = load_request()

    token = require_text(
        request_data,
        "authorizationToken",
    )
    username_hash = require_text(
        request_data,
        "usernameHash",
    )
    password_hash = require_text(
        request_data,
        "passwordHash",
    )

    digit_code = request_data.get("digitCode")

    if digit_code in (None, "", "string"):
        raise ValueError(
            "digitCode is missing."
        )

    digit_code = int(digit_code)

    claims = decode_token_payload(token)

    employee_id = str(
        claims.get("PersonnelNumber")
        or claims.get("employeeId")
        or claims.get("EmployeeID")
        or ""
    ).strip()

    if not employee_id:
        raise ValueError(
            "PersonnelNumber was not found in the token."
        )

    settings = get_settings()

    url = (
        f"{str(settings.hr_api_base_url).rstrip('/')}"
        f"/api/v{settings.api_version}"
        f"/Personnel/GetLeaveType"
    )

    verify_ssl = bool(
        getattr(settings, "verify_ssl", True)
    )

    token_value = (
        token[7:].strip()
        if token.lower().startswith("bearer ")
        else token
    )

    base_headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token_value}",
    }

    cases: list[
        tuple[
            str,
            dict[str, Any],
            dict[str, str],
        ]
    ] = [
        (
            "CASE_1_CURRENT_QUERY_CONTRACT",
            {
                "EmployeeID": employee_id,
                "UsernameHash": username_hash,
                "PasswordHash": password_hash,
                "digitCode": digit_code,
            },
            base_headers,
        ),
        (
            "CASE_2_LOWER_CAMEL_AUTH",
            {
                "EmployeeID": employee_id,
                "usernameHash": username_hash,
                "passwordHash": password_hash,
                "digitCode": digit_code,
            },
            base_headers,
        ),
        (
            "CASE_3_PASCAL_DIGIT",
            {
                "EmployeeID": employee_id,
                "UsernameHash": username_hash,
                "PasswordHash": password_hash,
                "DigitCode": digit_code,
            },
            base_headers,
        ),
        (
            "CASE_4_LOWER_EMPLOYEE_AND_AUTH",
            {
                "employeeID": employee_id,
                "usernameHash": username_hash,
                "passwordHash": password_hash,
                "digitCode": digit_code,
            },
            base_headers,
        ),
        (
            "CASE_5_EMPLOYEE_ID_CAMEL",
            {
                "employeeId": employee_id,
                "usernameHash": username_hash,
                "passwordHash": password_hash,
                "digitCode": digit_code,
            },
            base_headers,
        ),
        (
            "CASE_6_TOKEN_AND_EMPLOYEE_ONLY",
            {
                "EmployeeID": employee_id,
            },
            base_headers,
        ),
        (
            "CASE_7_AUTH_VALUES_IN_HEADERS",
            {
                "EmployeeID": employee_id,
            },
            {
                **base_headers,
                "UsernameHash": username_hash,
                "PasswordHash": password_hash,
                "digitCode": str(digit_code),
            },
        ),
    ]

    print(f"EMPLOYEE_ID={employee_id}")
    print(f"API_VERSION={settings.api_version}")
    print("TOKEN_FORMAT=OK")
    print("SECRETS_ARE_NOT_PRINTED=True")

    with httpx.Client(
        timeout=30,
        verify=verify_ssl,
        follow_redirects=False,
    ) as client:
        for label, params, headers in cases:
            response = client.get(
                url,
                params=params,
                headers=headers,
            )
            print_response(
                label,
                response,
            )


if __name__ == "__main__":
    main()