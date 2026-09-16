from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402
from app.infrastructure.repositories.state_repository import StateRepository  # noqa: E402

result = StateRepository(get_settings()).cleanup()
print(json.dumps(result, ensure_ascii=False))
