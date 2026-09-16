from pathlib import Path
import py_compile
import shutil

TARGET = Path(
    r"D:\serviceAi\app\api\routes\agent.py"
)

BACKUP = Path(
    r"D:\serviceAi\app\api\routes\agent.py.bak_before_response_fix_v2"
)

if not TARGET.exists():
    raise FileNotFoundError(
        f"Target file not found: {TARGET}"
    )

text = TARGET.read_text(
    encoding="utf-8"
)

old_block = '''        if legacy_bridge_call:
            if data.get("pendingAction") is not None:
                data["pendingAction"] = None

            if data.get("action") is not None:
                data["action"] = None
'''

new_block = '''        # Temporary compatibility for the current .NET response model.
        # The real action state remains stored inside Python.
        if "pendingAction" in data:
            data["pendingAction"] = None

        if "action" in data:
            data["action"] = None
'''

if old_block not in text:
    raise RuntimeError(
        "Expected compatibility block was not found. "
        "No file was changed."
    )

updated = text.replace(
    old_block,
    new_block,
    1,
)

candidate = Path(
    r"D:\serviceAi\agent_response_fix_v2_candidate.py"
)

candidate.write_text(
    updated,
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
    missing_ok=True,
)

print(f"BACKUP_OK={BACKUP}")
print(f"UPDATED_OK={TARGET}")
print("COMPILE_OK=True")