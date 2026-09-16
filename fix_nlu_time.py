from pathlib import Path


NLU_FILE = Path(
    r"D:\serviceAi\app\application\services\nlu_core.py"
)

BACKUP_FILE = Path(
    r"D:\serviceAi\app\application\services"
    r"\nlu_core_before_time_fix.py"
)


old_code = r'''    plain_hour_match = re.search(
        rf"(?:ساعت\s+)"
        rf"(?P<hour>{_HOUR_VALUE_PATTERN})",
        text,
    )
'''


new_code = r'''    if meridiem is not None:
        meridiem_pattern = (
            r"صبح|بامداد|ظهر|بعدازظهر|عصر|شب"
        )

        plain_hour_match = re.search(
            rf"(?:ساعت\s+)?"
            rf"(?P<hour>{_HOUR_VALUE_PATTERN})"
            rf"\s+(?:{meridiem_pattern})",
            text,
        )
    else:
        plain_hour_match = re.search(
            rf"(?:ساعت\s+)"
            rf"(?P<hour>{_HOUR_VALUE_PATTERN})",
            text,
        )
'''


if not NLU_FILE.exists():
    raise SystemExit(
        f"NLU_FILE_NOT_FOUND: {NLU_FILE}"
    )


content = NLU_FILE.read_text(
    encoding="utf-8"
)


if new_code in content:
    print("ALREADY_PATCHED")
    raise SystemExit(0)


if old_code not in content:
    raise SystemExit(
        "PATCH_TARGET_NOT_FOUND"
    )


BACKUP_FILE.write_text(
    content,
    encoding="utf-8",
)


updated_content = content.replace(
    old_code,
    new_code,
    1,
)


NLU_FILE.write_text(
    updated_content,
    encoding="utf-8",
)


print("PATCH_OK")
print(f"UPDATED_FILE={NLU_FILE}")
print(f"BACKUP_FILE={BACKUP_FILE}")