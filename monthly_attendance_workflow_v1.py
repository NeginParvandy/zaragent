from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(r"D:\serviceAi")

OUTPUT_DIR = (
    ROOT
    / "monthly_attendance_outputs"
)

WORKFLOW_DIR = (
    ROOT
    / "monthly_attendance_workflows"
)


def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def safe_date(
    value: str,
) -> str:
    return (
        value.strip()
        .replace("/", "-")
        .replace("\\", "-")
    )


def cards_file(
    start_date: str,
    end_date: str,
) -> Path:
    return (
        OUTPUT_DIR
        / (
            "monthly_attendance_cards_"
            f"{safe_date(start_date)}_"
            f"{safe_date(end_date)}.json"
        )
    )


def state_file(
    start_date: str,
    end_date: str,
) -> Path:
    return (
        WORKFLOW_DIR
        / (
            "monthly_attendance_workflow_"
            f"{safe_date(start_date)}_"
            f"{safe_date(end_date)}.json"
        )
    )


def load_json(
    path: Path,
) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(
            f"فایل پیدا نشد: {path}"
        )

    payload = json.loads(
        path.read_text(
            encoding="utf-8-sig"
        )
    )

    if not isinstance(
        payload,
        dict,
    ):
        raise ValueError(
            "ساختار فایل باید JSON Object باشد."
        )

    return payload


def write_json_atomic(
    path: Path,
    payload: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = path.with_suffix(
        path.suffix + ".tmp"
    )

    temporary.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    temporary.replace(path)


def issue_cards(
    cards_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    presentation = cards_payload.get(
        "presentation"
    )

    if not isinstance(
        presentation,
        dict,
    ):
        return []

    cards = presentation.get(
        "issueCards"
    )

    if not isinstance(
        cards,
        list,
    ):
        return []

    return [
        item
        for item in cards
        if isinstance(
            item,
            dict,
        )
    ]


def actions_for_card(
    card: dict[str, Any],
) -> list[dict[str, Any]]:
    interaction = card.get(
        "interaction"
    )

    if not isinstance(
        interaction,
        dict,
    ):
        return []

    actions = interaction.get(
        "actions"
    )

    if not isinstance(
        actions,
        list,
    ):
        return []

    return [
        item
        for item in actions
        if isinstance(
            item,
            dict,
        )
    ]


def create_state(
    cards_payload: dict[str, Any],
    source_file: Path,
) -> dict[str, Any]:
    cards = issue_cards(
        cards_payload
    )

    workflow_id = str(
        cards_payload.get(
            "workflowId",
            "",
        )
    ).strip()

    if not workflow_id:
        raise ValueError(
            "workflowId در فایل کارت‌ها وجود ندارد."
        )

    period = cards_payload.get(
        "period"
    )

    if not isinstance(
        period,
        dict,
    ):
        period = {}

    has_cards = bool(cards)

    return {
        "version": "1.0",
        "mode": "workflow-state-only",
        "workflowId": workflow_id,
        "workflowType": (
            "monthly_attendance_review"
        ),
        "period": period,
        "sourceCards": str(
            source_file
        ),
        "status": (
            "ACTIVE"
            if has_cards
            else "REVIEW_COMPLETE"
        ),
        "currentIndex": (
            0
            if has_cards
            else None
        ),
        "currentCardId": (
            str(
                cards[0].get(
                    "cardId",
                    "",
                )
            )
            if has_cards
            else None
        ),
        "totalCards": len(cards),
        "decisions": [],
        "createdAtUtc": utc_now(),
        "updatedAtUtc": utc_now(),
        "policy": {
            "writesToHr": False,
            "automaticMutationAllowed": False,
            "mutationRequiresPreview": True,
            "mutationRequiresExplicitConfirmation": (
                True
            ),
        },
    }


def current_card(
    cards: list[dict[str, Any]],
    state: dict[str, Any],
) -> dict[str, Any] | None:
    index = state.get(
        "currentIndex"
    )

    if index is None:
        return None

    if not isinstance(
        index,
        int,
    ):
        return None

    if not 0 <= index < len(cards):
        return None

    return cards[index]


def print_card(
    card: dict[str, Any],
) -> None:
    print("")
    print(
        str(
            card.get(
                "progressText",
                "",
            )
        )
    )

    print(
        str(
            card.get(
                "title",
                "مورد نیازمند بررسی",
            )
        )
    )

    print(
        str(
            card.get(
                "subtitle",
                "",
            )
        )
    )

    print(
        str(
            card.get(
                "description",
                "",
            )
        )
    )

    print("")

    facts = card.get(
        "facts"
    )

    if isinstance(
        facts,
        list,
    ):
        for fact in facts:
            if not isinstance(
                fact,
                dict,
            ):
                continue

            print(
                "- "
                f"{fact.get('label', '')}: "
                f"{fact.get('value', '')}"
            )

    print("")

    interaction = card.get(
        "interaction"
    )

    if isinstance(
        interaction,
        dict,
    ):
        print(
            str(
                interaction.get(
                    "prompt",
                    "یک گزینه را انتخاب کنید.",
                )
            )
        )

    actions = actions_for_card(
        card
    )

    for index, action in enumerate(
        actions,
        start=1,
    ):
        print(
            f"{index}. "
            f"{action.get('label', '')}"
        )


def command_init(
    start_date: str,
    end_date: str,
) -> None:
    source = cards_file(
        start_date,
        end_date,
    )

    target = state_file(
        start_date,
        end_date,
    )

    cards_payload = load_json(
        source
    )

    if target.exists():
        print(
            "WORKFLOW_ALREADY_EXISTS"
        )

        print(
            f"STATE_FILE={target}"
        )

        return

    state = create_state(
        cards_payload,
        source,
    )

    write_json_atomic(
        target,
        state,
    )

    print("WORKFLOW_INIT_OK")
    print(
        f"STATUS={state['status']}"
    )

    print(
        "TOTAL_CARDS="
        f"{state['totalCards']}"
    )

    print(
        f"STATE_FILE={target}"
    )


def command_show(
    start_date: str,
    end_date: str,
) -> None:
    source = cards_file(
        start_date,
        end_date,
    )

    target = state_file(
        start_date,
        end_date,
    )

    cards_payload = load_json(
        source
    )

    state = load_json(
        target
    )

    cards = issue_cards(
        cards_payload
    )

    print(
        "WORKFLOW_STATUS="
        f"{state.get('status', 'UNKNOWN')}"
    )

    if (
        state.get("status")
        == "REVIEW_COMPLETE"
    ):
        print(
            "همه موارد گزارش بررسی شده‌اند."
        )

        return

    card = current_card(
        cards,
        state,
    )

    if card is None:
        raise RuntimeError(
            "کارت جاری Workflow پیدا نشد."
        )

    print_card(card)


def command_select(
    start_date: str,
    end_date: str,
    option_number: int,
) -> None:
    source = cards_file(
        start_date,
        end_date,
    )

    target = state_file(
        start_date,
        end_date,
    )

    cards_payload = load_json(
        source
    )

    state = load_json(
        target
    )

    if state.get("status") != "ACTIVE":
        raise RuntimeError(
            "Workflow در وضعیت ACTIVE نیست."
        )

    cards = issue_cards(
        cards_payload
    )

    card = current_card(
        cards,
        state,
    )

    if card is None:
        raise RuntimeError(
            "کارت جاری پیدا نشد."
        )

    actions = actions_for_card(
        card
    )

    action_index = (
        option_number - 1
    )

    if not 0 <= action_index < len(actions):
        raise ValueError(
            "شماره گزینه نامعتبر است."
        )

    action = actions[
        action_index
    ]

    payload = action.get(
        "payload"
    )

    if not isinstance(
        payload,
        dict,
    ):
        payload = {}

    may_lead_to_mutation = bool(
        action.get(
            "mayLeadToMutation",
            False,
        )
    )

    decision = {
        "decisionId": (
            f"{card.get('cardId', '')}-"
            f"{action.get('actionId', '')}"
        ),
        "cardId": str(
            card.get(
                "cardId",
                "",
            )
        ),
        "date": str(
            payload.get(
                "date",
                "",
            )
        ),
        "weekday": str(
            payload.get(
                "weekday",
                "",
            )
        ),
        "issueType": str(
            payload.get(
                "issueType",
                "",
            )
        ),
        "actionId": str(
            action.get(
                "actionId",
                "",
            )
        ),
        "label": str(
            action.get(
                "label",
                "",
            )
        ),
        "command": str(
            action.get(
                "command",
                "",
            )
        ),
        "nextStep": str(
            action.get(
                "nextStep",
                "",
            )
        ),
        "mayLeadToMutation": (
            may_lead_to_mutation
        ),
        "requiresPreviewBeforeMutation": bool(
            action.get(
                "requiresPreviewBeforeMutation",
                False,
            )
        ),
        "requiresExplicitConfirmation": bool(
            action.get(
                "requiresExplicitConfirmation",
                False,
            )
        ),
        "decisionStatus": (
            "AWAITING_DETAILS"
            if may_lead_to_mutation
            else "RESOLVED"
        ),
        "selectedAtUtc": utc_now(),
    }

    decisions = state.get(
        "decisions"
    )

    if not isinstance(
        decisions,
        list,
    ):
        decisions = []

    decisions.append(
        decision
    )

    state["decisions"] = decisions

    current_index = int(
        state.get(
            "currentIndex",
            0,
        )
    )

    next_index = (
        current_index + 1
    )

    if next_index >= len(cards):
        state["status"] = (
            "REVIEW_COMPLETE"
        )

        state["currentIndex"] = None
        state["currentCardId"] = None

    else:
        state["currentIndex"] = (
            next_index
        )

        state["currentCardId"] = str(
            cards[next_index].get(
                "cardId",
                "",
            )
        )

    state["updatedAtUtc"] = (
        utc_now()
    )

    write_json_atomic(
        target,
        state,
    )

    print("SELECTION_SAVED")
    print(
        "SELECTED_CARD_ID="
        f"{decision['cardId']}"
    )

    print(
        "SELECTED_LABEL="
        f"{decision['label']}"
    )

    print(
        "NEXT_STEP="
        f"{decision['nextStep']}"
    )

    print(
        "WRITES_TO_HR=False"
    )

    print(
        "WORKFLOW_STATUS="
        f"{state['status']}"
    )

    if (
        state["status"]
        == "ACTIVE"
    ):
        print(
            "NEXT_CARD_ID="
            f"{state['currentCardId']}"
        )

    else:
        print(
            "REVIEW_COMPLETE"
        )


def command_status(
    start_date: str,
    end_date: str,
) -> None:
    target = state_file(
        start_date,
        end_date,
    )

    state = load_json(
        target
    )

    decisions = state.get(
        "decisions"
    )

    if not isinstance(
        decisions,
        list,
    ):
        decisions = []

    awaiting_details = sum(
        1
        for item in decisions
        if isinstance(item, dict)
        and item.get(
            "decisionStatus"
        )
        == "AWAITING_DETAILS"
    )

    resolved = sum(
        1
        for item in decisions
        if isinstance(item, dict)
        and item.get(
            "decisionStatus"
        )
        == "RESOLVED"
    )

    print(
        "WORKFLOW_ID="
        f"{state.get('workflowId', '')}"
    )

    print(
        "STATUS="
        f"{state.get('status', '')}"
    )

    print(
        "TOTAL_CARDS="
        f"{state.get('totalCards', 0)}"
    )

    print(
        "DECISION_COUNT="
        f"{len(decisions)}"
    )

    print(
        "AWAITING_DETAILS_COUNT="
        f"{awaiting_details}"
    )

    print(
        "RESOLVED_COUNT="
        f"{resolved}"
    )

    print(
        "CURRENT_CARD_ID="
        f"{state.get('currentCardId') or ''}"
    )

    print(
        f"STATE_FILE={target}"
    )


def command_reset(
    start_date: str,
    end_date: str,
) -> None:
    target = state_file(
        start_date,
        end_date,
    )

    if not target.exists():
        print(
            "WORKFLOW_STATE_NOT_FOUND"
        )

        return

    target.unlink()

    print("WORKFLOW_RESET_OK")
    print(
        "WRITES_TO_HR=False"
    )


def print_usage() -> None:
    print(
        "USAGE:"
    )

    print(
        "  monthly_attendance_workflow_v1.py "
        "init START_DATE END_DATE"
    )

    print(
        "  monthly_attendance_workflow_v1.py "
        "show START_DATE END_DATE"
    )

    print(
        "  monthly_attendance_workflow_v1.py "
        "select START_DATE END_DATE OPTION_NUMBER"
    )

    print(
        "  monthly_attendance_workflow_v1.py "
        "status START_DATE END_DATE"
    )

    print(
        "  monthly_attendance_workflow_v1.py "
        "reset START_DATE END_DATE"
    )


def main() -> None:
    if len(sys.argv) < 4:
        print_usage()
        raise SystemExit(2)

    command = (
        sys.argv[1]
        .strip()
        .lower()
    )

    start_date = (
        sys.argv[2].strip()
    )

    end_date = (
        sys.argv[3].strip()
    )

    if command == "init":
        if len(sys.argv) != 4:
            print_usage()
            raise SystemExit(2)

        command_init(
            start_date,
            end_date,
        )

        return

    if command == "show":
        if len(sys.argv) != 4:
            print_usage()
            raise SystemExit(2)

        command_show(
            start_date,
            end_date,
        )

        return

    if command == "select":
        if len(sys.argv) != 5:
            print_usage()
            raise SystemExit(2)

        try:
            option_number = int(
                sys.argv[4]
            )

        except ValueError as exc:
            raise ValueError(
                "OPTION_NUMBER باید عدد باشد."
            ) from exc

        command_select(
            start_date,
            end_date,
            option_number,
        )

        return

    if command == "status":
        if len(sys.argv) != 4:
            print_usage()
            raise SystemExit(2)

        command_status(
            start_date,
            end_date,
        )

        return

    if command == "reset":
        if len(sys.argv) != 4:
            print_usage()
            raise SystemExit(2)

        command_reset(
            start_date,
            end_date,
        )

        return

    print_usage()
    raise SystemExit(2)


if __name__ == "__main__":
    main()