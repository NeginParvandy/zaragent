from __future__ import annotations

import ast
import hashlib
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path


ROOT_DIR = Path(r"D:\serviceAi")

TARGET_FILE = (
    ROOT_DIR
    / "app"
    / "application"
    / "services"
    / "chat_service.py"
)

FORMATTER_FILE = (
    ROOT_DIR
    / "app"
    / "application"
    / "services"
    / "leave_balance_formatter.py"
)


IMPORT_LINE = (
    "from app.application.services."
    "leave_balance_formatter import "
    "format_leave_balance_reply"
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def syntax_inventory(
    source: str,
) -> dict[str, list[str]]:
    tree = ast.parse(
        source,
        filename=str(TARGET_FILE),
    )

    classes: list[str] = []
    functions: list[str] = []
    async_functions: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes.append(node.name)

        elif isinstance(node, ast.AsyncFunctionDef):
            async_functions.append(node.name)

        elif isinstance(node, ast.FunctionDef):
            functions.append(node.name)

    return {
        "classes": sorted(classes),
        "functions": sorted(functions),
        "asyncFunctions": sorted(
            async_functions
        ),
    }


def fail(message: str) -> None:
    print("")
    print("FAILED")
    print(message)
    sys.exit(1)


def main() -> None:
    if not TARGET_FILE.exists():
        fail(
            f"Target file was not found: "
            f"{TARGET_FILE}"
        )

    if not FORMATTER_FILE.exists():
        fail(
            f"Formatter file was not found: "
            f"{FORMATTER_FILE}"
        )

    original_bytes = TARGET_FILE.read_bytes()

    had_utf8_bom = original_bytes.startswith(
        b"\xef\xbb\xbf"
    )

    try:
        original_source = original_bytes.decode(
            "utf-8-sig"
        )
    except UnicodeDecodeError as exc:
        fail(
            "chat_service.py is not valid UTF-8: "
            f"{exc}"
        )

    newline = (
        "\r\n"
        if "\r\n" in original_source
        else "\n"
    )

    try:
        original_inventory = syntax_inventory(
            original_source
        )
    except SyntaxError as exc:
        fail(
            "Current chat_service.py has a syntax "
            f"error before patching: {exc}"
        )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    backup_file = TARGET_FILE.with_name(
        "chat_service.py."
        f"bak_before_leave_balance_{timestamp}"
    )

    shutil.copy2(
        TARGET_FILE,
        backup_file,
    )

    import_anchor = (
        "from app.application.services."
        "hr_service import HrService"
    )

    old_block_lines = [
        "        if self._is_leave_balance(text):",
        "            data = await self.hr.get_time_account(",
        "                context,",
        "                dates[0] if dates else str(context.date),",
        "            )",
        "            return {",
        (
            '                "reply": '
            '"اطلاعات مانده مرخصی دریافت شد.",'
        ),
        (
            '                "requiresConfirmation": '
            "False,"
        ),
        (
            '                "data": '
            'data.get("data", data),'
        ),
        "            }",
    ]

    new_block_lines = [
        "        if self._is_leave_balance(text):",
        "            data = await self.hr.get_time_account(",
        "                context,",
        "                dates[0] if dates else str(context.date),",
        "            )",
        "",
        (
            '            rows = '
            'data.get("data", data)'
        ),
        "",
        "            return {",
        (
            '                "reply": '
            "format_leave_balance_reply(rows),"
        ),
        (
            '                "requiresConfirmation": '
            "False,"
        ),
        '                "data": rows,',
        "            }",
    ]

    old_block = newline.join(
        old_block_lines
    )

    new_block = newline.join(
        new_block_lines
    )

    working_source = original_source

    import_count = working_source.count(
        IMPORT_LINE
    )

    if import_count > 1:
        fail(
            "Formatter import already exists more "
            "than once. No change was made."
        )

    if import_count == 0:
        anchor_count = working_source.count(
            import_anchor
        )

        if anchor_count != 1:
            fail(
                "Expected exactly one HrService "
                "import anchor, but found "
                f"{anchor_count}. No change was made."
            )

        working_source = working_source.replace(
            import_anchor,
            (
                import_anchor
                + newline
                + IMPORT_LINE
            ),
            1,
        )

    old_block_count = working_source.count(
        old_block
    )

    new_block_count = working_source.count(
        new_block
    )

    if (
        old_block_count == 0
        and new_block_count == 1
    ):
        print("")
        print("ALREADY_APPLIED")
        print(
            "Leave balance formatter integration "
            "is already present."
        )
        print(f"Backup: {backup_file}")
        return

    if old_block_count != 1:
        fail(
            "Expected exactly one old leave-balance "
            "block, but found "
            f"{old_block_count}. "
            "No project file was changed."
        )

    working_source = working_source.replace(
        old_block,
        new_block,
        1,
    )

    if working_source.count(IMPORT_LINE) != 1:
        fail(
            "Formatter import validation failed. "
            "No project file was changed."
        )

    if working_source.count(
        "format_leave_balance_reply(rows)"
    ) != 1:
        fail(
            "Formatter call validation failed. "
            "No project file was changed."
        )

    if (
        "اطلاعات مانده مرخصی دریافت شد."
        in working_source
    ):
        fail(
            "The old fixed reply still exists. "
            "No project file was changed."
        )

    try:
        new_inventory = syntax_inventory(
            working_source
        )

        compile(
            working_source,
            str(TARGET_FILE),
            "exec",
        )

    except SyntaxError as exc:
        fail(
            "Patched source did not pass syntax "
            f"validation: {exc}"
        )

    if new_inventory != original_inventory:
        fail(
            "Class/function inventory changed "
            "unexpectedly. No project file was changed."
        )

    encoded_source = working_source.encode(
        "utf-8"
    )

    if had_utf8_bom:
        encoded_source = (
            b"\xef\xbb\xbf"
            + encoded_source
        )

    temporary_file = TARGET_FILE.with_name(
        "chat_service.py.tmp_leave_balance"
    )

    if temporary_file.exists():
        temporary_file.unlink()

    temporary_file.write_bytes(
        encoded_source
    )

    try:
        temporary_bytes = (
            temporary_file.read_bytes()
        )

        temporary_source = (
            temporary_bytes.decode("utf-8-sig")
        )

        compile(
            temporary_source,
            str(TARGET_FILE),
            "exec",
        )

        if syntax_inventory(
            temporary_source
        ) != original_inventory:
            raise RuntimeError(
                "Temporary file inventory mismatch."
            )

        os.replace(
            temporary_file,
            TARGET_FILE,
        )

        stored_bytes = TARGET_FILE.read_bytes()
        stored_source = stored_bytes.decode(
            "utf-8-sig"
        )

        compile(
            stored_source,
            str(TARGET_FILE),
            "exec",
        )

        if stored_source.count(
            IMPORT_LINE
        ) != 1:
            raise RuntimeError(
                "Stored import validation failed."
            )

        if stored_source.count(
            "format_leave_balance_reply(rows)"
        ) != 1:
            raise RuntimeError(
                "Stored formatter call validation "
                "failed."
            )

        if syntax_inventory(
            stored_source
        ) != original_inventory:
            raise RuntimeError(
                "Stored class/function inventory "
                "changed unexpectedly."
            )

    except Exception as exc:
        if temporary_file.exists():
            temporary_file.unlink()

        shutil.copy2(
            backup_file,
            TARGET_FILE,
        )

        fail(
            "Post-write validation failed. "
            "The backup was restored automatically. "
            f"Reason: {exc}"
        )

    print("")
    print("SUCCESS")
    print(
        "Leave balance formatter was integrated "
        "safely."
    )
    print(f"Target: {TARGET_FILE}")
    print(f"Backup: {backup_file}")
    print(
        "Before SHA256: "
        f"{sha256_bytes(original_bytes)}"
    )
    print(
        "After SHA256:  "
        f"{sha256_bytes(TARGET_FILE.read_bytes())}"
    )
    print(
        "Classes and functions were preserved."
    )
    print(
        "No API route, request model, or response "
        "contract was changed."
    )


if __name__ == "__main__":
    main()