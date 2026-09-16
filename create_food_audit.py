# -*- coding: utf-8 -*-

from pathlib import Path


ROOT = Path(r"D:\serviceAi")

SOURCE_FILES = [
    ROOT / "app" / "application" / "services" / "chat_service.py",
    ROOT / "app" / "application" / "services" / "food_service.py",
    ROOT / "app" / "application" / "services" / "nlu_core.py",
    ROOT / "app" / "application" / "services" / "action_service.py",
    ROOT / "app" / "api" / "routes" / "agent.py",
]

OUTPUT = ROOT / "food_audit_current_sources.txt"

sections = []

for path in SOURCE_FILES:
    if not path.exists():
        sections.extend(
            [
                "",
                "=" * 80,
                f"FILE_NOT_FOUND: {path}",
                "=" * 80,
            ]
        )
        continue

    lines = path.read_text(
        encoding="utf-8-sig"
    ).splitlines()

    sections.extend(
        [
            "",
            "=" * 80,
            f"FILE: {path}",
            f"TOTAL_LINES: {len(lines)}",
            "=" * 80,
        ]
    )

    sections.extend(
        f"{line_number:05d}: {line}"
        for line_number, line in enumerate(
            lines,
            start=1,
        )
    )

OUTPUT.write_text(
    "\n".join(sections),
    encoding="utf-8",
)

print("AUDIT_OK")
print(f"OUTPUT={OUTPUT}")