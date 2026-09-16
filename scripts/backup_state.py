from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402


def verify(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"Backup not found: {path}")
    with sqlite3.connect(path) as connection:
        result = connection.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise SystemExit(f"Integrity check failed: {result}")
    print(f"Backup verified: {path}")


def backup() -> Path:
    settings = get_settings()
    source_path = settings.sqlite_file
    if not source_path.exists():
        raise SystemExit(f"State database not found: {source_path}")
    backup_dir = source_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    target_path = backup_dir / f"{source_path.stem}_{datetime.now():%Y%m%d_%H%M%S}.db"
    with sqlite3.connect(source_path) as source, sqlite3.connect(target_path) as target:
        source.backup(target)
    verify(target_path)
    return target_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-only", type=Path)
    args = parser.parse_args()
    if args.verify_only:
        verify(args.verify_only.resolve())
        return
    print(f"Backup created: {backup()}")


if __name__ == "__main__":
    main()
