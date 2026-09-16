from __future__ import annotations

import hmac
import re
from collections.abc import Iterable

from pydantic import SecretStr

SENSITIVE_PATTERN = re.compile(r'(?i)(authorization|token|passwordhash|usernamehash|digitcode|api[_-]?key)(["\s:=]+)([^&\s,}\"]+)')


def secret_value(value: object) -> str:
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    return "" if value is None else str(value)


def mask_secret(value: object, visible: int = 3) -> str:
    text = secret_value(value)
    if not text:
        return ""
    if len(text) <= visible * 2:
        return "***"
    return f"{text[:visible]}***{text[-visible:]}"


def sanitize_text(text: object, secrets: Iterable[object] | None = None, limit: int = 1200) -> str:
    safe = "" if text is None else str(text)
    for secret in secrets or []:
        raw = secret_value(secret)
        if raw:
            safe = safe.replace(raw, mask_secret(raw))
    safe = SENSITIVE_PATTERN.sub(lambda m: f"{m.group(1)}{m.group(2)}***", safe)
    if len(safe) > limit:
        return safe[:limit] + "..."
    return safe


def normalize_bearer_token(token: object | None) -> str:
    raw = secret_value(token).strip()
    if not raw:
        return ""
    if raw.lower().startswith("bearer "):
        return raw
    return f"Bearer {raw}"


def secure_equals(left: object, right: object) -> bool:
    left_text = secret_value(left)
    right_text = secret_value(right)
    return bool(left_text and right_text and hmac.compare_digest(left_text, right_text))
