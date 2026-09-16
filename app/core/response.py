from __future__ import annotations

from typing import Any


def ok(data: Any = None, message: str = "") -> dict[str, Any]:
    return {"hasError": False, "data": data, "message": message, "error": None}
