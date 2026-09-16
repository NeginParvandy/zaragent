from pathlib import Path
import py_compile
import shutil


TARGET = Path(
    r"D:\serviceAi\app\application\services\hr_service.py"
)

BACKUP = Path(
    r"D:\serviceAi\app\application\services\hr_service.py.bak_before_leave_span_trace"
)

if not TARGET.exists():
    raise FileNotFoundError(f"File not found: {TARGET}")

text = TARGET.read_text(encoding="utf-8")

if "LEAVE_SPAN_RESULT" in text:
    print("TRACE_ALREADY_INSTALLED=True")
    raise SystemExit(0)

if "import logging\n" not in text:
    text = text.replace(
        "import json\n",
        "import json\nimport logging\n",
        1,
    )

class_marker = "\n\nclass HrService:"

if "logger = logging.getLogger(__name__)" not in text:
    if class_marker not in text:
        raise RuntimeError("Class marker not found.")

    text = text.replace(
        class_marker,
        "\n\nlogger = logging.getLogger(__name__)" + class_marker,
        1,
    )

old = '''            await self.calculate_leave_span(context, absence_code, info_type, start_date, end_date, safe_start_time, safe_end_time)
            await self.get_quota_available(context, absence_code, info_type)
'''

new = '''            span_result = await self.calculate_leave_span(
                context,
                absence_code,
                info_type,
                start_date,
                end_date,
                safe_start_time,
                safe_end_time,
            )

            logger.warning(
                (
                    "LEAVE_SPAN_RESULT employee_id=%s "
                    "absence_type_code=%s result=%r"
                ),
                context.employee_id,
                absence_code,
                span_result,
            )

            await self.get_quota_available(
                context,
                absence_code,
                info_type,
            )
'''

if old not in text:
    raise RuntimeError(
        "CalculateLeaveSpan marker not found. No file changed."
    )

text = text.replace(old, new, 1)

candidate = Path(
    r"D:\serviceAi\hr_service_leave_span_candidate.py"
)

candidate.write_text(text, encoding="utf-8")

py_compile.compile(
    str(candidate),
    doraise=True,
)

shutil.copy2(TARGET, BACKUP)
shutil.copy2(candidate, TARGET)

py_compile.compile(
    str(TARGET),
    doraise=True,
)

candidate.unlink(missing_ok=True)

print(f"BACKUP_OK={BACKUP}")
print(f"UPDATED_OK={TARGET}")
print("COMPILE_OK=True")