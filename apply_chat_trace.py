from pathlib import Path
import py_compile
import shutil

target = Path(r"D:\serviceAi\app\api\routes\agent.py")
backup = Path(r"D:\serviceAi\app\api\routes\agent.py.bak_before_chat_trace")

if not target.exists():
    raise FileNotFoundError(f"File not found: {target}")

text = target.read_text(encoding="utf-8")

if "CHAT_TRACE_START" in text:
    print("TRACE_ALREADY_INSTALLED=True")
    raise SystemExit(0)

if "import logging\n" not in text:
    import_marker = "import hashlib\n"

    if import_marker not in text:
        raise RuntimeError("Import marker not found. No changes made.")

    text = text.replace(
        import_marker,
        import_marker + "import logging\n",
        1,
    )

if "logger = logging.getLogger(__name__)" not in text:
    router_marker = "\nrouter = APIRouter("

    if router_marker not in text:
        raise RuntimeError("Router marker not found. No changes made.")

    text = text.replace(
        router_marker,
        "\nlogger = logging.getLogger(__name__)\n" + router_marker,
        1,
    )

old_block = """    data = await container.chat_service.handle(
        context,
        request.message,
    )
"""

new_block = """    session = context.session

    logger.info(
        (
            "CHAT_TRACE_START employee_id=%s "
            "conversation_id=%s message_length=%s "
            "has_token=%s has_username_hash=%s "
            "has_password_hash=%s has_digit_code=%s"
        ),
        context.employee_id,
        context.conversation_id,
        len(request.message or ""),
        bool(session and session.authorization_token),
        bool(session and session.username_hash),
        bool(session and session.password_hash),
        bool(session and session.digit_code),
    )

    try:
        data = await container.chat_service.handle(
            context,
            request.message,
        )
    except Exception as exc:
        logger.exception(
            (
                "CHAT_TRACE_FAILURE employee_id=%s "
                "conversation_id=%s exception_type=%s "
                "code=%s status_code=%s details=%r"
            ),
            context.employee_id,
            context.conversation_id,
            type(exc).__name__,
            getattr(exc, "code", None),
            getattr(exc, "status_code", None),
            getattr(exc, "details", None),
        )
        raise

    logger.info(
        (
            "CHAT_TRACE_SUCCESS employee_id=%s "
            "conversation_id=%s keys=%s "
            "requires_confirmation=%s "
            "pending_action_present=%s"
        ),
        context.employee_id,
        context.conversation_id,
        sorted(data.keys()) if isinstance(data, dict) else [],
        (
            data.get("requiresConfirmation")
            if isinstance(data, dict)
            else None
        ),
        (
            bool(data.get("pendingAction"))
            if isinstance(data, dict)
            else False
        ),
    )
"""

if old_block not in text:
    raise RuntimeError("Chat handler block not found. No changes made.")

text = text.replace(old_block, new_block, 1)

candidate = Path(r"D:\serviceAi\agent_chat_trace_candidate.py")
candidate.write_text(text, encoding="utf-8")

py_compile.compile(str(candidate), doraise=True)

shutil.copy2(target, backup)
shutil.copy2(candidate, target)

py_compile.compile(str(target), doraise=True)

candidate.unlink(missing_ok=True)

print(f"BACKUP_OK={backup}")
print(f"UPDATED_OK={target}")
print("COMPILE_OK=True")a