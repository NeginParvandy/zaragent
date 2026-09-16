# -*- coding: cp1256 -*-
from pathlib import Path


OUTPUT = Path(
    r"D:\serviceAi\food_memory_nlu_context.txt"
)

SPECS = [
    (
        "CHAT_PENDING_ACTION",
        Path(
            r"D:\serviceAi\app\application"
            r"\services\chat_service.py"
        ),
        "pendingActionId",
        25,
        80,
        4,
    ),
    (
        "CHAT_RECENT_MENUS",
        Path(
            r"D:\serviceAi\app\application"
            r"\services\chat_service.py"
        ),
        "recentMenus",
        25,
        100,
        5,
    ),
    (
        "CHAT_SAVE_PAYLOAD",
        Path(
            r"D:\serviceAi\app\application"
            r"\services\chat_service.py"
        ),
        "_save_conversation_payload(",
        20,
        90,
        5,
    ),
    (
        "NLU_RESERVE_FOOD",
        Path(
            r"D:\serviceAi\app\application"
            r"\services\nlu_core.py"
        ),
        "RESERVE_FOOD",
        30,
        130,
        6,
    ),
    (
        "NLU_REGISTER_WORDS",
        Path(
            r"D:\serviceAi\app\application"
            r"\services\nlu_core.py"
        ),
        "ثبت غذا",
        30,
        100,
        4,
    ),
]


def extract_sections(
    title: str,
    path: Path,
    marker: str,
    before: int,
    after: int,
    limit: int,
) -> list[str]:
    lines = path.read_text(
        encoding="utf-8-sig"
    ).splitlines()

    indexes = [
        index
        for index, line in enumerate(lines)
        if marker in line
    ]

    output: list[str] = []

    if not indexes:
        output.extend(
            [
                "",
                f"=== {title} ===",
                f"MARKER_NOT_FOUND: {marker}",
            ]
        )
        return output

    for occurrence, index in enumerate(
        indexes[:limit],
        start=1,
    ):
        start = max(
            0,
            index - before,
        )
        end = min(
            len(lines),
            index + after,
        )

        output.extend(
            [
                "",
                (
                    f"=== {title} "
                    f"#{occurrence} ==="
                ),
                f"FILE: {path}",
                f"MARKER: {marker}",
            ]
        )

        output.extend(
            f"{line_number + 1}: "
            f"{lines[line_number]}"
            for line_number in range(
                start,
                end,
            )
        )

    return output


result: list[str] = []

for spec in SPECS:
    result.extend(
        extract_sections(*spec)
    )

OUTPUT.write_text(
    "\n".join(result),
    encoding="utf-8",
)

print("EXTRACT_OK")
print(f"OUTPUT={OUTPUT}")