from __future__ import annotations

import contextvars
import json
import logging
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

from pydantic import SecretStr

from app.core.config import Settings
from app.core.security import mask_secret, sanitize_text

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


def _sanitize_log_value(value: Any) -> Any:
    if isinstance(value, SecretStr):
        return mask_secret(value)
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, dict):
        return {key: _sanitize_log_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_sanitize_log_value(item) for item in value)
    if isinstance(value, list):
        return [_sanitize_log_value(item) for item in value]
    return value


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        sanitized_args = _sanitize_log_value(record.args)
        try:
            rendered = str(record.msg) % sanitized_args if sanitized_args else str(record.msg)
        except (TypeError, ValueError):
            rendered = f"{record.msg} {sanitized_args}"
        record.msg = sanitize_text(rendered)
        record.args = ()
        record.request_id = request_id_var.get("-")
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "requestId": getattr(record, "request_id", "-"),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(settings: Settings) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    formatter = JsonFormatter()
    redaction = RedactionFilter()

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.addFilter(redaction)
    root.addHandler(console)

    log_path: Path = settings.log_file
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = TimedRotatingFileHandler(
        log_path,
        when="midnight",
        backupCount=settings.log_backup_count,
        encoding="utf-8",
        utc=True,
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(redaction)
    root.addHandler(file_handler)

    for noisy_logger in ("httpx", "httpcore", "hpack", "urllib3"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
