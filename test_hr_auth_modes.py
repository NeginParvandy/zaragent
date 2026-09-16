from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx

from app.core.config import get_settings


def decode_token_payload(token: str) -> dict:
    token_value = token.strip()

    if token_value.lower().startswith("bearer "):
        token_value = token_value[7:].strip()

    parts = token_value.split(".")
    if len(parts) < 2:
        raise ValueError("authorizationToken is not a JWT.")

    payload = parts[1]
    payload += "=" * ((4 - len(payload) % 4) % 4)

    return json.loads(
        base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8")
    )


request_data = json.loads(
    Path(r"D:\serviceAi\request_test.json").read_text(
        encoding="utf-8-sig"
    )
)

token = str(request_data.get("authorizationToken") or "").strip()
username_hash = str(request_data.get("usernameHash") or "").strip()
password_hash = str(request_data.get("passwordHash") or "").strip()
digit_code = request_data.get("digitCode")

claims = decode_token_payload(token)

employee_id = str(
    claims.get("PersonnelNumber")
    or claims.get("employeeId")
    or claims.get("EmployeeID")
    or ""
).strip()

if not employee_id:
    raise ValueError("PersonnelNumber was not found in the token.")

settings = get_settings()

url = (
    f"{str(settings.hr_api_base_url).rstrip('/')}"
    f"/api/v{settings.api_version}/Personnel/GetTimeAccount"
)

params = {
    "EmployeeID": employee_id,
    "Date": "1405/04/25",
    "UsernameHash": username_hash,
    "PasswordHash": password_hash,
    "digitCode": int(digit_code),
}

verify_ssl = bool(getattr(settings, "verify_ssl", True))

token_value = token[7:].strip() if token.lower().startswith("bearer ") else token


def run_test(label: str, headers: dict[str, str]) -> None:
    with httpx.Client(
        timeout=30,
        verify=verify_ssl,
        follow_redirects=False,
    ) as client:
        response = client.get(
            url,
            params=params,
            headers=headers,
        )

    print(f"{label}_STATUS={response.status_code}")

    try:
        payload = response.json()
        print(f"{label}_HAS_ERROR={payload.get('hasError')}")
        print(f"{label}_MESSAGE={payload.get('message')}")
        print(f"{label}_DATA_TYPE={type(payload.get('data')).__name__}")
    except Exception:
        print(f"{label}_JSON_RESPONSE=False")


run_test(
    "NO_AUTH",
    {
        "Accept": "application/json",
    },
)

run_test(
    "USER_TOKEN",
    {
        "Accept": "application/json",
        "Authorization": f"Bearer {token_value}",
    },
)