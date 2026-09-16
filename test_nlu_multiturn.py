from __future__ import annotations

import json

from app.application.services.nlu_core import analyze_message


REFERENCE_DATE = "1405/04/30"


def show_step(title: str, result: dict) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)
    print(json.dumps(result, ensure_ascii=False, indent=2))


step1 = analyze_message(
    "برای 9 مرداد تردد ثبت کن",
    reference_date=REFERENCE_DATE,
)

show_step(
    "STEP 1 - initial request",
    step1,
)


step2 = analyze_message(
    "8 صبح",
    reference_date=REFERENCE_DATE,
    conversation_state=step1["state"],
)

show_step(
    "STEP 2 - time supplied",
    step2,
)


step3 = analyze_message(
    "ورود",
    reference_date=REFERENCE_DATE,
    conversation_state=step2["state"],
)

show_step(
    "STEP 3 - event type supplied",
    step3,
)


step4 = analyze_message(
    "بله",
    reference_date=REFERENCE_DATE,
    conversation_state=step3["state"],
)

show_step(
    "STEP 4 - confirmation",
    step4,
)


assert step1["entities"]["date"] == "1405/05/09"
assert step1["missingFields"] == [
    "time",
    "eventType",
]

assert step2["entities"]["time"] == "08:00"
assert step2["missingFields"] == [
    "eventType",
]

assert step3["entities"] == {
    "date": "1405/05/09",
    "time": "08:00",
    "eventType": "ENTRY",
}

assert step3["missingFields"] == []
assert step3["conversationComplete"] is False

assert step4["intent"] == "CONFIRM"

assert (
    step4["entities"]["parentIntent"]
    == "CREATE_TIME_EVENT"
)

assert step4["conversationComplete"] is True

print("\nTEST_RESULT=OK")