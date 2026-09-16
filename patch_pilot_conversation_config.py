from __future__ import annotations

import json
import py_compile
import shutil
import traceback
from pathlib import Path


ROOT = Path(r"D:\serviceAi")

AGENT_PATH = (
    ROOT
    / "app"
    / "api"
    / "routes"
    / "agent.py"
)

CONFIG_PATH = (
    ROOT
    / "pilot_hr_override.json"
)

AGENT_BACKUP = Path(
    str(AGENT_PATH)
    + ".bak_before_pilot_conversation_config"
)

CONFIG_BACKUP = Path(
    str(CONFIG_PATH)
    + ".bak_before_pilot_conversation_config"
)

MARKER = (
    "# PILOT_CONVERSATION_CONFIG_V1"
)


OLD_BLOCK = '''    conversation_id = str(
        context.conversation_id or ""
    ).strip()

    if conversation_id != "pilot-05000602":
'''


NEW_BLOCK = '''    # PILOT_CONVERSATION_CONFIG_V1
    configured_conversation_id = str(
        config.get(
            "conversationId",
            "pilot-05000602",
        )
        or "pilot-05000602"
    ).strip()

    conversation_id = str(
        context.conversation_id or ""
    ).strip()

    if (
        conversation_id
        != configured_conversation_id
    ):
'''


def restore_files() -> None:
    if AGENT_BACKUP.exists():
        shutil.copy2(
            AGENT_BACKUP,
            AGENT_PATH,
        )

    if CONFIG_BACKUP.exists():
        shutil.copy2(
            CONFIG_BACKUP,
            CONFIG_PATH,
        )


try:
    if not AGENT_PATH.exists():
        raise FileNotFoundError(
            f"Agent file not found: {AGENT_PATH}"
        )

    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Config file not found: {CONFIG_PATH}"
        )

    shutil.copy2(
        AGENT_PATH,
        AGENT_BACKUP,
    )

    shutil.copy2(
        CONFIG_PATH,
        CONFIG_BACKUP,
    )

    agent_text = AGENT_PATH.read_text(
        encoding="utf-8-sig"
    )

    config_text = CONFIG_PATH.read_text(
        encoding="utf-8-sig"
    )

    config = json.loads(config_text)

    if not isinstance(config, dict):
        raise RuntimeError(
            "pilot_hr_override.json "
            "must contain a JSON object"
        )

    configured_id = str(
        config.get(
            "conversationId",
            "",
        )
        or ""
    ).strip()

    if not configured_id:
        config["conversationId"] = (
            "pilot-05000602"
        )

    if MARKER not in agent_text:
        occurrence_count = (
            agent_text.count(OLD_BLOCK)
        )

        if occurrence_count != 1:
            raise RuntimeError(
                "agent conversation anchor: "
                f"expected 1 occurrence, "
                f"found {occurrence_count}"
            )

        agent_text = agent_text.replace(
            OLD_BLOCK,
            NEW_BLOCK,
            1,
        )

    AGENT_PATH.write_text(
        agent_text,
        encoding="utf-8",
        newline="\n",
    )

    CONFIG_PATH.write_text(
        json.dumps(
            config,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    py_compile.compile(
        str(AGENT_PATH),
        doraise=True,
    )

    verified_agent = (
        AGENT_PATH.read_text(
            encoding="utf-8-sig"
        )
    )

    verified_config = json.loads(
        CONFIG_PATH.read_text(
            encoding="utf-8-sig"
        )
    )

    if MARKER not in verified_agent:
        raise RuntimeError(
            "Agent marker verification failed"
        )

    if not str(
        verified_config.get(
            "conversationId",
            "",
        )
        or ""
    ).strip():
        raise RuntimeError(
            "conversationId verification failed"
        )

    print("PATCH_OK")
    print(
        "PILOT_CONVERSATION_CONFIG_TESTS_OK"
    )
    print(
        f"AGENT_BACKUP={AGENT_BACKUP}"
    )
    print(
        f"CONFIG_BACKUP={CONFIG_BACKUP}"
    )

except Exception:
    restore_files()

    print("PATCH_FAILED_ROLLED_BACK")
    traceback.print_exc()
    raise