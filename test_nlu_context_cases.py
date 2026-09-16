from app.application.services.nlu_core import analyze_message

food_state = {
    "domain": "FOOD",
    "intent": "RESERVE_FOOD",
    "entities": {
        "date": "1405/05/09",
        "foodName": "مرغ",
    },
    "missingFields": [],
    "needsClarification": False,
    "conversationComplete": False,
}

tests = [
    ("رزرو غذا", None),
    ("مرغ رو رزرو کن", food_state),
    ("نه", food_state),
    ("خیر", food_state),
    ("میخوام مرخصی ثبت کنم", food_state),
    ("ثبت تردد برای فردا ساعت 8", None),
]

for message, state in tests:
    result = analyze_message(
        message,
        reference_date="1405/05/01",
        conversation_state=state,
    )

    print("--------------------------------")
    print("MESSAGE=", message)
    print("DOMAIN=", result.get("domain"))
    print("INTENT=", result.get("intent"))
    print("ENTITIES=", result.get("entities"))
    print("MISSING=", result.get("missingFields"))
    print("CLARIFICATION=", result.get("clarification"))
    print("COMPLETE=", result.get("conversationComplete"))
