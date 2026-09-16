from pathlib import Path
import py_compile
import shutil


TARGET = Path(r"D:\serviceAi\app\api\routes\agent.py")
BACKUP = Path(
    r"D:\serviceAi\app\api\routes\agent.py.bak_before_hr_business_message"
)

if not TARGET.exists():
    raise FileNotFoundError(
        f"Target file not found: {TARGET}"
    )

text = TARGET.read_text(encoding="utf-8")

if "HR_BUSINESS_MESSAGE_FUTURE_ATTENDANCE" in text:
    print("PATCH_ALREADY_INSTALLED=True")
    raise SystemExit(0)


# Import IntegrationError if it is not already imported.
integration_import = (
    "from app.core.exceptions import IntegrationError\n"
)

if integration_import not in text:
    logger_marker = "logger = logging.getLogger(__name__)\n"

    if logger_marker not in text:
        raise RuntimeError(
            "Logger marker not found. No file was changed."
        )

    text = text.replace(
        logger_marker,
        integration_import + "\n" + logger_marker,
        1,
    )


old_block = '''        data = await container.chat_service.handle(
            context,
            request.message,
        )
    except Exception as exc:
'''

new_block = '''        data = await container.chat_service.handle(
            context,
            request.message,
        )
    except IntegrationError as exc:
        details = getattr(
            exc,
            "details",
            None,
        ) or {}

        downstream_path = str(
            details.get(
                "path",
                "",
            )
        )

        downstream_status = details.get(
            "downstreamStatusCode"
        )

        if (
            downstream_path.endswith(
                "/PostTimeEventSet"
            )
            and downstream_status == 400
        ):
            # HR_BUSINESS_MESSAGE_FUTURE_ATTENDANCE
            logger.warning(
                (
                    "HR_BUSINESS_MESSAGE_FUTURE_ATTENDANCE "
                    "employee_id=%s conversation_id=%s"
                ),
                context.employee_id,
                context.conversation_id,
            )

            data = {
                "reply": (
                    "ثبت تردد انجام نشد. "
                    "امکان ثبت تردد برای روزهای آینده وجود ندارد. "
                    "لطفاً تاریخ امروز یا یکی از روزهای گذشته را وارد کنید."
                ),
                "requiresConfirmation": False,
                "pendingAction": None,
                "data": None,
            }
        else:
            logger.exception(
                (
                    "CHAT_TRACE_FAILURE employee_id=%s "
                    "conversation_id=%s exception_type=%s "
                    "code=%s status_code=%s details=%r"
                ),
                context.employee_id,
                context.conversation_id,
                type(exc).__name__,
                getattr(
                    exc,
                    "code",
                    None,
                ),
                getattr(
                    exc,
                    "status_code",
                    None,
                ),
                details,
            )
            raise
    except Exception as exc:
'''

if old_block not in text:
    raise RuntimeError(
        "Chat handler marker not found. No file was changed."
    )

text = text.replace(
    old_block,
    new_block,
    1,
)


candidate = Path(
    r"D:\serviceAi\agent_hr_business_message_candidate.py"
)

candidate.write_text(
    text,
    encoding="utf-8",
)

py_compile.compile(
    str(candidate),
    doraise=True,
)

shutil.copy2(
    TARGET,
    BACKUP,
)

shutil.copy2(
    candidate,
    TARGET,
)

py_compile.compile(
    str(TARGET),
    doraise=True,
)

candidate.unlink(
    missing_ok=True
)

print(f"BACKUP_OK={BACKUP}")
print(f"UPDATED_OK={TARGET}")
print("COMPILE_OK=True")