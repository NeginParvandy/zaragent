from __future__ import annotations

import py_compile
import shutil
import traceback
from pathlib import Path


ROOT = Path(r"D:\serviceAi")

CHAT_PATH = (
    ROOT
    / "app"
    / "application"
    / "services"
    / "chat_service.py"
)

BACKUP_PATH = Path(
    str(CHAT_PATH)
    + ".bak_before_food_router_domain_guard"
)

MARKER = (
    "# FOOD_ROUTER_DOMAIN_GUARD_V1"
)


GUARD_LINES = [
    "        # FOOD_ROUTER_DOMAIN_GUARD_V1",
    "        # An explicit non-food NLU result must",
    "        # never be converted into a food command.",
    "        detected_domain = str(",
    '            result.get("domain")',
    '            or ""',
    "        ).strip().upper()",
    "",
    "        if detected_domain in {",
    '            "LEAVE",',
    '            "MISSION",',
    '            "ATTENDANCE",',
    "        }:",
    "            return result",
    "",
]


def restore_file() -> None:
    if BACKUP_PATH.exists():
        shutil.copy2(
            BACKUP_PATH,
            CHAT_PATH,
        )


try:
    if not CHAT_PATH.exists():
        raise FileNotFoundError(
            f"Chat service not found: {CHAT_PATH}"
        )

    shutil.copy2(
        CHAT_PATH,
        BACKUP_PATH,
    )

    original_text = CHAT_PATH.read_text(
        encoding="utf-8-sig"
    )

    had_trailing_newline = (
        original_text.endswith("\n")
    )

    lines = original_text.splitlines()

    if MARKER not in original_text:
        method_indexes = [
            index
            for index, line in enumerate(lines)
            if line.strip()
            == "def _override_explicit_food_command("
        ]

        if len(method_indexes) != 1:
            raise RuntimeError(
                "_override_explicit_food_command "
                f"anchor: found {len(method_indexes)}"
            )

        method_index = method_indexes[0]

        normalized_indexes = [
            index
            for index in range(
                method_index,
                min(
                    len(lines),
                    method_index + 100,
                ),
            )
            if lines[index].strip()
            == "normalized = normalize_nlu_text("
        ]

        if len(normalized_indexes) != 1:
            raise RuntimeError(
                "normalized anchor inside food router: "
                f"found {len(normalized_indexes)}"
            )

        insert_index = normalized_indexes[0]

        lines[
            insert_index:
            insert_index
        ] = GUARD_LINES

    updated_text = "\n".join(lines)

    if had_trailing_newline:
        updated_text += "\n"

    CHAT_PATH.write_text(
        updated_text,
        encoding="utf-8",
        newline="\n",
    )

    py_compile.compile(
        str(CHAT_PATH),
        doraise=True,
    )

    verified_text = CHAT_PATH.read_text(
        encoding="utf-8-sig"
    )

    if MARKER not in verified_text:
        raise RuntimeError(
            "Food router domain guard "
            "verification failed"
        )

    required_fragments = [
        '            "LEAVE",',
        '            "MISSION",',
        '            "ATTENDANCE",',
        "            return result",
    ]

    for fragment in required_fragments:
        if fragment not in verified_text:
            raise RuntimeError(
                "Required guard fragment "
                f"was not found: {fragment}"
            )

    print("PATCH_OK")
    print(
        "FOOD_ROUTER_DOMAIN_GUARD_TESTS_OK"
    )
    print(
        f"CHAT_BACKUP={BACKUP_PATH}"
    )

except Exception:
    restore_file()

    print("PATCH_FAILED_ROLLED_BACK")
    traceback.print_exc()
    raise