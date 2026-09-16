from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Holding Smart Agent")
    parser.add_argument("--mode", choices=("development", "production"), default="production")
    args = parser.parse_args()

    if args.mode == "development":
        os.environ["APP_ENV"] = "development"
        os.environ["APP_DEBUG"] = "true"
        os.environ["ENABLE_DOCS"] = "true"
        os.environ["AUTH_REQUIRED"] = "false"
        os.environ["FORCE_HTTPS"] = "false"

    from app.core.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    settings.validate_runtime()

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=args.mode == "development",
        workers=1,
        proxy_headers=args.mode == "production",
        forwarded_allow_ips=settings.forwarded_allow_ips if args.mode == "production" else "127.0.0.1",
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    main()
