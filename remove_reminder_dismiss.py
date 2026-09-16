from pathlib import Path
import re


ROOT = Path(r"D:\serviceAi")

AGENT_ROUTE_FILE = (
    ROOT / "app" / "api" / "routes" / "agent.py"
)

REMINDER_SERVICE_FILE = (
    ROOT
    / "app"
    / "application"
    / "services"
    / "reminder_service.py"
)

MODELS_FILE = (
    ROOT / "app" / "domain" / "models.py"
)

REPOSITORY_FILE = (
    ROOT
    / "app"
    / "infrastructure"
    / "repositories"
    / "state_repository.py"
)


def replace_regex_once(
    text: str,
    pattern: str,
    replacement: str,
    label: str,
) -> str:
    updated, count = re.subn(
        pattern,
        replacement,
        text,
        count=1,
        flags=re.MULTILINE | re.DOTALL,
    )

    if count != 1:
        raise RuntimeError(
            f"{label}: expected exactly one match, "
            f"found {count}"
        )

    return updated


def patch_agent_route(text: str) -> str:
    text = replace_regex_once(
        text,
        r"^[ \t]*ReminderDismissRequest,\n",
        "",
        "remove ReminderDismissRequest import",
    )

    text = replace_regex_once(
        text,
        (
            r"\n@router\.post\(\n"
            r"[ \t]*\"/reminders/dismiss\","
            r".*?"
            r"\n(?=@router\.post\(\n"
            r"[ \t]*\"/chat\")"
        ),
        "\n",
        "remove reminders dismiss route",
    )

    return text


def patch_models(text: str) -> str:
    return replace_regex_once(
        text,
        (
            r"\nclass ReminderDismissRequest"
            r"\(EmployeeRequestBase\):"
            r".*?"
            r"(?=\nclass )"
        ),
        "\n",
        "remove ReminderDismissRequest model",
    )


def patch_reminder_service(text: str) -> str:
    text = replace_regex_once(
        text,
        (
            r"^from app\.core\.exceptions "
            r"import NotFoundError\n"
        ),
        "",
        "remove NotFoundError import",
    )

    text = replace_regex_once(
        text,
        (
            r"\n    async def dismiss\("
            r".*?"
            r"(?=\n    def _build_records\()"
        ),
        "\n",
        "remove ReminderService dismiss method",
    )

    return text


def patch_repository(text: str) -> str:
    return replace_regex_once(
        text,
        (
            r"\n    def dismiss_reminder\("
            r".*?"
            r"(?=\n    def cleanup\()"
        ),
        "\n",
        "remove repository dismiss method",
    )


def main() -> None:
    agent_route = AGENT_ROUTE_FILE.read_text(
        encoding="utf-8"
    )

    reminder_service = (
        REMINDER_SERVICE_FILE.read_text(
            encoding="utf-8"
        )
    )

    models = MODELS_FILE.read_text(
        encoding="utf-8"
    )

    repository = REPOSITORY_FILE.read_text(
        encoding="utf-8"
    )

    agent_route = patch_agent_route(agent_route)

    reminder_service = patch_reminder_service(
        reminder_service
    )

    models = patch_models(models)

    repository = patch_repository(repository)

    AGENT_ROUTE_FILE.write_text(
        agent_route,
        encoding="utf-8",
    )

    REMINDER_SERVICE_FILE.write_text(
        reminder_service,
        encoding="utf-8",
    )

    MODELS_FILE.write_text(
        models,
        encoding="utf-8",
    )

    REPOSITORY_FILE.write_text(
        repository,
        encoding="utf-8",
    )

    print("REMINDER DISMISS REMOVED SUCCESSFULLY")
    print("Modified files:")
    print(AGENT_ROUTE_FILE)
    print(REMINDER_SERVICE_FILE)
    print(MODELS_FILE)
    print(REPOSITORY_FILE)


if __name__ == "__main__":
    main()