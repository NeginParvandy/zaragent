from __future__ import annotations

import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402


def verify(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        result = connection.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise SystemExit(f"Integrity check failed: {result}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/restore_state.py <backup.db>")
    backup_path = Path(sys.argv[1]).expanduser().resolve()
    if not backup_path.exists():
        raise SystemExit(f"Backup not found: {backup_path}")
    verify(backup_path)

    target = get_settings().sqlite_file
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        safety = target.parent / "backups" / f"{target.stem}_before_restore_{datetime.now():%Y%m%d_%H%M%S}.db"
        safety.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(target) as source, sqlite3.connect(safety) as destination:
            source.backup(destination)
        verify(safety)
        print(f"Safety backup created: {safety}")

    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(target) + suffix)
        if sidecar.exists():
            sidecar.unlink()
    shutil.copy2(backup_path, target)
    verify(target)
    print(f"State restored: {target}")


if __name__ == "__main__":
    main()
