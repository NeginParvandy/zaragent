from pathlib import Path
import py_compile
import shutil

TARGET = Path(
    r"D:\serviceAi\app\api\routes\agent.py"
)

BACKUP = Path(
    r"D:\serviceAi\app\api\routes\agent.py.bak_before_bridge_response_fix"
)

CANDIDATE = Path(
    r"D:\serviceAi\agent_bridge_full_compat_candidate.py"
)

if not TARGET.exists():
    raise FileNotFoundError(
        f"Target file not found: {TARGET}"
    )

text = TARGET.read_text(
    encoding="utf-8"
)

old_context_block = '''    if (
        not raw_context.conversation_id
        and request.conversation_id
    ):
        raw_context.conversation_id = (
            request.conversation_id
        )

    context = container.context_resolver.resolve(
'''

new_context_block = '''    if (
        not raw_context.conversation_id
        and request.conversation_id
    ):
        raw_context.conversation_id = (
            request.conversation_id
        )

    legacy_bridge_call = not bool(
        raw_context.conversation_id
        or request.conversation_id
    )

    context = container.context_resolver.resolve(
'''

old_response_block = '''    # Compatibility shim for the current .NET AgentData contract.
    if (
        isinstance(data, dict)
        and data.get("data") is not None
    ):
        data = dict(data)
        data["data"] = None

    return ok(
'''

new_response_block = '''    # Compatibility shim for the current .NET AgentData contract.
    # Stateful chat data remains stored server-side.
    # Legacy callers can continue with natural-language follow-ups.
    if isinstance(data, dict):
        data = dict(data)

        if data.get("data") is not None:
            data["data"] = None

        if legacy_bridge_call:
            if data.get("pendingAction") is not None:
                data["pendingAction"] = None

            if data.get("action") is not None:
                data["action"] = None

    return ok(
'''

if "legacy_bridge_call = not bool(" not in text:
    if old_context_block not in text:
        raise RuntimeError(
            "Conversation block was not found; "
            "no file was changed."
        )

    text = text.replace(
        old_context_block,
        new_context_block,
        1,
    )

if "if legacy_bridge_call:" not in text:
    if old_response_block not in text:
        raise RuntimeError(
            "Response compatibility block was not found; "
            "no file was changed."
        )

    text = text.replace(
        old_response_block,
        new_response_block,
        1,
    )

CANDIDATE.write_text(
    text,
    encoding="utf-8",
)

py_compile.compile(
    str(CANDIDATE),
    doraise=True,
)

shutil.copy2(
    TARGET,
    BACKUP,
)

shutil.copy2(
    CANDIDATE,
    TARGET,
)

py_compile.compile(
    str(TARGET),
    doraise=True,
)

CANDIDATE.unlink(
    missing_ok=True,
)

print(f"BACKUP_OK={BACKUP}")
print(f"UPDATED_OK={TARGET}")
print("COMPILE_OK=True")