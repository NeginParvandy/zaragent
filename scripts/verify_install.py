from __future__ import annotations

import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    if sys.version_info < (3, 10) or sys.version_info >= (3, 15):
        raise SystemExit("Unsupported Python. Use Python 3.10-3.14; Python 3.13 is recommended.")

    import fastapi
    import httpx
    import pydantic

    from app.application.container import get_container
    from app.core.config import get_settings
    from app.domain.text import normalize_jalali_date

    settings = get_settings()
    container = get_container()
    database = container.repository.health_check()
    if database.get("database") != "ok":
        raise RuntimeError("SQLite health check failed during installation verification.")
    if normalize_jalali_date("۱۴۰۵/۰۴/۲۲") != "1405/04/22":
        raise RuntimeError("Persian date normalization check failed.")
    print(f"Python: {platform.python_version()}")
    print(f"FastAPI: {fastapi.__version__}")
    print(f"HTTPX: {httpx.__version__}")
    print(f"Pydantic: {pydantic.__version__}")
    print(f"Agent: {settings.app_version}")
    print("Installation verification passed.")


if __name__ == "__main__":
    main()
