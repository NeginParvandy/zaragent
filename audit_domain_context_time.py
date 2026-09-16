# -*- coding: utf-8 -*-

from __future__ import annotations

import ast
import hashlib
import importlib
import json
import py_compile
import re
import shutil
import sys
import traceback
import zipfile
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(r"D:\serviceAi")

OUTPUT_DIR = (
    ROOT
    / "domain_context_time_audit_bundle"
)

REPORT_JSON = (
    OUTPUT_DIR
    / "audit_report.json"
)

REPORT_TEXT = (
    OUTPUT_DIR
    / "audit_report.txt"
)

ZIP_PATH = (
    ROOT
    / "domain_context_time_audit_bundle.zip"
)

REFERENCE_DATE = "1405/05/02"


SOURCE_FILES = [
    (
        ROOT
        / "app"
        / "application"
        / "services"
        / "chat_service.py"
    ),
    (
        ROOT
        / "app"
        / "application"
        / "services"
        / "nlu_core.py"
    ),
    (
        ROOT
        / "app"
        / "application"
        / "services"
        / "intent_guard.py"
    ),
    (
        ROOT
        / "app"
        / "application"
        / "services"
        / "action_service.py"
    ),
    (
        ROOT
        / "app"
        / "domain"
        / "text.py"
    ),
    (
        ROOT
        / "app"
        / "domain"
        / "models.py"
    ),
    (
        ROOT
        / "app"
        / "infrastructure"
        / "repositories"
        / "state_repository.py"
    ),
    (
        ROOT
        / "app"
        / "core"
        / "config.py"
    ),
]


TARGET_FUNCTIONS = {
    "chat_service.py": {
        "handle",
        "_load_conversation_payload",
        "_save_conversation_payload",
        "_delete_conversation_state",
        "_finalize_response_state",
        "_combined_conversation_text",
        "_cancel_pending_on_domain_switch",
        "_nlu_state_with_active_date",
        "_enrich_food_nlu_result",
        "_handle_pending_action_reply",
        "_handle_attendance",
        "_prepare_create_leave",
    },
    "nlu_core.py": {
        "analyze_message",
        "normalize_text",
        "_detect_domain",
        "_detect_intent",
        "_extract_time_entities",
        "_extract_date_entities",
        "_required_fields",
        "_clarification_message",
        "_build_state",
    },
    "intent_guard.py": {
        "analyze",
    },
    "text.py": {
        "extract_times",
        "extract_jalali_dates",
        "normalize_persian_text",
    },
    "state_repository.py": {
        "save_chat_state",
        "get_chat_state",
        "delete_chat_state",
    },
}


SEARCH_TERMS = [
    "CONVERSATION_STATE_TTL_MINUTES",
    "FOOD_CHAT_STATE_TTL_MINUTES",
    "intent_guard.analyze",
    "_load_conversation_payload",
    "_save_conversation_payload",
    "nluState",
    "lastDomain",
    "originalMessage",
    "missingFields",
    "needsClarification",
    "conversationComplete",
    "previous_state",
    "conversation_state",
    "extract_times",
    "extract_jalali_dates",
    "صبح",
    "شب",
    "نیم",
    "چهل و پنج",
    "مرداد",
    "اسحقاقی",
    "استحقاقی",
    "ترد",
    "تردد",
    "FOOD",
    "LEAVE",
    "MISSION",
    "ATTENDANCE",
]


def safe_value(
    value: Any,
) -> Any:
    if value is None:
        return None

    if isinstance(
        value,
        (
            str,
            int,
            float,
            bool,
        ),
    ):
        return value

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, dict):
        return {
            str(key): safe_value(item)
            for key, item in value.items()
        }

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
        ),
    ):
        return [
            safe_value(item)
            for item in value
        ]

    if is_dataclass(value):
        return safe_value(
            asdict(value)
        )

    if hasattr(value, "model_dump"):
        try:
            return safe_value(
                value.model_dump()
            )
        except Exception:
            pass

    if hasattr(value, "dict"):
        try:
            return safe_value(
                value.dict()
            )
        except Exception:
            pass

    if hasattr(value, "__dict__"):
        try:
            return safe_value(
                vars(value)
            )
        except Exception:
            pass

    return str(value)


def sha256_file(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(
                1024 * 1024
            ),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def file_metadata(
    path: Path,
) -> dict[str, Any]:
    stat = path.stat()

    return {
        "path": str(path),
        "relativePath": str(
            path.relative_to(ROOT)
        ),
        "sizeBytes": stat.st_size,
        "modifiedEpoch": (
            stat.st_mtime
        ),
        "modifiedLocal": (
            datetime.fromtimestamp(
                stat.st_mtime
            ).isoformat(
                timespec="seconds"
            )
        ),
        "sha256": sha256_file(path),
    }


def copy_source(
    path: Path,
) -> Path:
    relative = path.relative_to(ROOT)

    destination = (
        OUTPUT_DIR
        / "source"
        / relative
    )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        path,
        destination,
    )

    return destination


def syntax_check(
    path: Path,
) -> dict[str, Any]:
    try:
        py_compile.compile(
            str(path),
            doraise=True,
        )

        return {
            "ok": True,
            "error": None,
        }

    except Exception as exc:
        return {
            "ok": False,
            "error": (
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        }


def source_constants(
    text: str,
) -> dict[str, str]:
    constants: dict[str, str] = {}

    pattern = re.compile(
        r"(?m)^([A-Z][A-Z0-9_]+)"
        r"\s*=\s*(.+)$"
    )

    for match in pattern.finditer(
        text
    ):
        name = match.group(1)

        if any(
            token in name
            for token in (
                "TTL",
                "STATE",
                "TIME",
                "DOMAIN",
                "INTENT",
            )
        ):
            constants[name] = (
                match.group(2).strip()
            )

    return constants


def source_markers(
    text: str,
) -> list[str]:
    markers = []

    for line in text.splitlines():
        stripped = line.strip()

        if (
            stripped.startswith("#")
            and any(
                token in stripped
                for token in (
                    "_V",
                    "PATCH",
                    "FINAL",
                    "FIX",
                    "ROUTER",
                    "GUARD",
                    "NEGATIVE",
                    "CHANGE",
                )
            )
        ):
            markers.append(stripped)

    return markers


def function_ranges(
    path: Path,
    text: str,
) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(
            text,
            filename=str(path),
        )
    except SyntaxError:
        return []

    wanted = TARGET_FUNCTIONS.get(
        path.name,
        set(),
    )

    results = []

    for node in ast.walk(tree):
        if not isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        ):
            continue

        include = node.name in wanted

        if path.name == "nlu_core.py":
            include = include or any(
                token in node.name.lower()
                for token in (
                    "time",
                    "date",
                    "domain",
                    "intent",
                    "clarif",
                    "state",
                )
            )

        if not include:
            continue

        results.append(
            {
                "name": node.name,
                "startLine": (
                    node.lineno
                ),
                "endLine": (
                    getattr(
                        node,
                        "end_lineno",
                        node.lineno,
                    )
                ),
                "async": isinstance(
                    node,
                    ast.AsyncFunctionDef,
                ),
            }
        )

    results.sort(
        key=lambda item: (
            item["startLine"]
        )
    )

    return results


def search_snippets(
    path: Path,
    text: str,
) -> list[dict[str, Any]]:
    lines = text.splitlines()
    results = []

    for term in SEARCH_TERMS:
        matched_lines = [
            index
            for index, line in enumerate(
                lines,
                start=1,
            )
            if term in line
        ]

        if not matched_lines:
            continue

        for line_number in (
            matched_lines[:8]
        ):
            start = max(
                1,
                line_number - 3,
            )

            end = min(
                len(lines),
                line_number + 3,
            )

            snippet = "\n".join(
                (
                    f"{number:05d}: "
                    f"{lines[number - 1]}"
                )
                for number in range(
                    start,
                    end + 1,
                )
            )

            results.append(
                {
                    "file": str(path),
                    "term": term,
                    "line": line_number,
                    "snippet": snippet,
                }
            )

    return results


def import_current(
    module_name: str,
):
    if module_name in sys.modules:
        del sys.modules[module_name]

    importlib.invalidate_caches()

    return importlib.import_module(
        module_name
    )


def entity_values(
    result: dict[str, Any],
) -> dict[str, Any]:
    entities = result.get(
        "entities"
    )

    return (
        dict(entities)
        if isinstance(
            entities,
            dict,
        )
        else {}
    )


def nlu_summary(
    result: Any,
) -> dict[str, Any]:
    safe = safe_value(result)

    if not isinstance(safe, dict):
        return {
            "raw": safe,
        }

    return {
        "domain": safe.get("domain"),
        "intent": safe.get("intent"),
        "entities": safe.get(
            "entities"
        ),
        "missingFields": safe.get(
            "missingFields"
        ),
        "needsClarification": (
            safe.get(
                "needsClarification"
            )
        ),
        "clarification": safe.get(
            "clarification"
        ),
        "errors": safe.get("errors"),
        "state": safe.get("state"),
        "confidence": safe.get(
            "confidence"
        ),
    }


def contains_time(
    result: dict[str, Any],
    expected: str,
) -> bool:
    entities = entity_values(result)

    values = {
        str(value)
        for key, value in (
            entities.items()
        )
        if "time" in key.lower()
        and value is not None
    }

    return expected in values


def contains_date(
    result: dict[str, Any],
    expected: str,
) -> bool:
    entities = entity_values(result)

    values = {
        str(value)
        for key, value in (
            entities.items()
        )
        if "date" in key.lower()
        and value is not None
    }

    return expected in values


def run_nlu_audit() -> dict[str, Any]:
    report: dict[str, Any] = {
        "importOk": False,
        "direct": [],
        "sequential": [],
        "checks": [],
        "error": None,
    }

    try:
        module = import_current(
            "app.application.services.nlu_core"
        )

        analyze_message = getattr(
            module,
            "analyze_message",
        )

        normalize_text = getattr(
            module,
            "normalize_text",
            None,
        )

        report["importOk"] = True

    except Exception:
        report["error"] = (
            traceback.format_exc()
        )

        return report

    def analyze(
        message: str,
        state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return analyze_message(
            message,
            reference_date=(
                REFERENCE_DATE
            ),
            conversation_state=state,
        )

    food_state = {
        "domain": "FOOD",
        "intent": "RESERVE_FOOD",
        "entities": {
            "date": "1405/05/03",
        },
        "missingFields": [
            "food",
        ],
    }

    leave_state = {
        "domain": "LEAVE",
        "intent": "CREATE_LEAVE",
        "entities": {
            "leaveType": (
                "استحقاقی"
            ),
        },
        "missingFields": [
            "startDate",
        ],
    }

    attendance_state = {
        "domain": "ATTENDANCE",
        "intent": "CREATE_TIME_EVENT",
        "entities": {
            "date": "1405/05/03",
        },
        "missingFields": [
            "time",
        ],
    }

    direct_cases = [
        {
            "name": (
                "leave_explicit_with_food_memory"
            ),
            "message": (
                "میخوام مرخصی استحقاقی "
                "ثبت کنم برای فردا"
            ),
            "state": food_state,
            "expectedDomain": "LEAVE",
            "expectedIntent": (
                "CREATE_LEAVE"
            ),
        },
        {
            "name": (
                "leave_typo_with_food_memory"
            ),
            "message": (
                "مرخصی اسحقاقی "
                "برای فردا"
            ),
            "state": food_state,
            "expectedDomain": "LEAVE",
            "expectedIntent": (
                "CREATE_LEAVE"
            ),
        },
        {
            "name": "leave_explicit",
            "message": (
                "ثبت مرخصی استحقاقی "
                "برای فردا"
            ),
            "state": None,
            "expectedDomain": "LEAVE",
            "expectedIntent": (
                "CREATE_LEAVE"
            ),
        },
        {
            "name": (
                "attendance_plain"
            ),
            "message": (
                "تردد برای فردا"
            ),
            "state": None,
            "expectedDomain": (
                "ATTENDANCE"
            ),
            "expectedIntent": None,
        },
        {
            "name": (
                "attendance_typo_create"
            ),
            "message": (
                "ثبت ترد برای فردا"
            ),
            "state": None,
            "expectedDomain": (
                "ATTENDANCE"
            ),
            "expectedIntent": (
                "CREATE_TIME_EVENT"
            ),
        },
        {
            "name": (
                "attendance_explicit_create"
            ),
            "message": (
                "ثبت تردد برای فردا"
            ),
            "state": None,
            "expectedDomain": (
                "ATTENDANCE"
            ),
            "expectedIntent": (
                "CREATE_TIME_EVENT"
            ),
        },
        {
            "name": (
                "attendance_switch_from_leave"
            ),
            "message": (
                "ثبت تردد برای فردا "
                "ساعت 8 صبح"
            ),
            "state": leave_state,
            "expectedDomain": (
                "ATTENDANCE"
            ),
            "expectedIntent": (
                "CREATE_TIME_EVENT"
            ),
        },
        {
            "name": (
                "leave_switch_from_attendance"
            ),
            "message": (
                "ثبت مرخصی استحقاقی "
                "برای 4 مرداد"
            ),
            "state": attendance_state,
            "expectedDomain": "LEAVE",
            "expectedIntent": (
                "CREATE_LEAVE"
            ),
        },
    ]

    for case in direct_cases:
        try:
            result = analyze(
                case["message"],
                case["state"],
            )

            summary = nlu_summary(
                result
            )

            normalized = (
                normalize_text(
                    case["message"]
                )
                if callable(
                    normalize_text
                )
                else None
            )

            expected_domain = (
                case[
                    "expectedDomain"
                ]
            )

            expected_intent = (
                case[
                    "expectedIntent"
                ]
            )

            domain_ok = (
                summary.get("domain")
                == expected_domain
            )

            intent_ok = (
                True
                if expected_intent
                is None
                else (
                    summary.get("intent")
                    == expected_intent
                )
            )

            report["direct"].append(
                {
                    "name": case["name"],
                    "message": (
                        case["message"]
                    ),
                    "normalized": (
                        normalized
                    ),
                    "inputState": (
                        case["state"]
                    ),
                    "expectedDomain": (
                        expected_domain
                    ),
                    "expectedIntent": (
                        expected_intent
                    ),
                    "domainOk": domain_ok,
                    "intentOk": intent_ok,
                    "passed": (
                        domain_ok
                        and intent_ok
                    ),
                    "result": summary,
                }
            )

        except Exception:
            report["direct"].append(
                {
                    "name": case["name"],
                    "message": (
                        case["message"]
                    ),
                    "passed": False,
                    "exception": (
                        traceback.format_exc()
                    ),
                }
            )

    try:
        attendance_start = analyze(
            "ثبت تردد برای فردا",
            None,
        )

        base_attendance_state = (
            attendance_start.get(
                "state"
            )
            if isinstance(
                attendance_start,
                dict,
            )
            else None
        )

    except Exception:
        attendance_start = {}
        base_attendance_state = None

    time_followups = [
        {
            "message": "8",
            "expectedTime": None,
            "mustClarifyPeriod": True,
        },
        {
            "message": "۸",
            "expectedTime": None,
            "mustClarifyPeriod": True,
        },
        {
            "message": "8 صبح",
            "expectedTime": "08:00",
            "mustClarifyPeriod": False,
        },
        {
            "message": "۸ صبح",
            "expectedTime": "08:00",
            "mustClarifyPeriod": False,
        },
        {
            "message": "8 شب",
            "expectedTime": "20:00",
            "mustClarifyPeriod": False,
        },
        {
            "message": "8 و نیم صبح",
            "expectedTime": "08:30",
            "mustClarifyPeriod": False,
        },
        {
            "message": "8 و نیم شب",
            "expectedTime": "20:30",
            "mustClarifyPeriod": False,
        },
        {
            "message": (
                "8 و چهل و پنج دقیقه صبح"
            ),
            "expectedTime": "08:45",
            "mustClarifyPeriod": False,
        },
        {
            "message": (
                "8 و چهل و پنج دقیقه شب"
            ),
            "expectedTime": "20:45",
            "mustClarifyPeriod": False,
        },
        {
            "message": (
                "10 و پنجاه دقیقه شب"
            ),
            "expectedTime": "22:50",
            "mustClarifyPeriod": False,
        },
        {
            "message": "20:15",
            "expectedTime": "20:15",
            "mustClarifyPeriod": False,
        },
    ]

    for item in time_followups:
        try:
            result = analyze(
                item["message"],
                base_attendance_state,
            )

            summary = nlu_summary(
                result
            )

            expected_time = (
                item["expectedTime"]
            )

            time_ok = (
                True
                if expected_time is None
                else contains_time(
                    result,
                    expected_time,
                )
            )

            domain_ok = (
                summary.get("domain")
                == "ATTENDANCE"
            )

            clarification_text = str(
                summary.get(
                    "clarification"
                )
                or ""
            )

            if item[
                "mustClarifyPeriod"
            ]:
                period_ok = (
                    bool(
                        summary.get(
                            "needsClarification"
                        )
                    )
                    and "صبح"
                    in clarification_text
                    and "شب"
                    in clarification_text
                )
            else:
                period_ok = True

            report[
                "sequential"
            ].append(
                {
                    "group": (
                        "attendance_time"
                    ),
                    "message": (
                        item["message"]
                    ),
                    "baseState": (
                        base_attendance_state
                    ),
                    "expectedTime": (
                        expected_time
                    ),
                    "domainOk": domain_ok,
                    "timeOk": time_ok,
                    "periodClarificationOk": (
                        period_ok
                    ),
                    "passed": (
                        domain_ok
                        and time_ok
                        and period_ok
                    ),
                    "result": summary,
                }
            )

        except Exception:
            report[
                "sequential"
            ].append(
                {
                    "group": (
                        "attendance_time"
                    ),
                    "message": (
                        item["message"]
                    ),
                    "passed": False,
                    "exception": (
                        traceback.format_exc()
                    ),
                }
            )

    try:
        leave_start = analyze(
            "ثبت مرخصی استحقاقی",
            None,
        )

        base_leave_state = (
            leave_start.get("state")
            if isinstance(
                leave_start,
                dict,
            )
            else None
        )

    except Exception:
        leave_start = {}
        base_leave_state = None

    date_followups = [
        {
            "message": "4 مرداد",
            "expectedDate": (
                "1405/05/04"
            ),
        },
        {
            "message": "۴ مرداد",
            "expectedDate": (
                "1405/05/04"
            ),
        },
        {
            "message": (
                "چهارم مرداد"
            ),
            "expectedDate": (
                "1405/05/04"
            ),
        },
        {
            "message": "فردا",
            "expectedDate": (
                "1405/05/03"
            ),
        },
        {
            "message": "پس فردا",
            "expectedDate": (
                "1405/05/04"
            ),
        },
    ]

    for item in date_followups:
        try:
            result = analyze(
                item["message"],
                base_leave_state,
            )

            summary = nlu_summary(
                result
            )

            domain_ok = (
                summary.get("domain")
                == "LEAVE"
            )

            date_ok = contains_date(
                result,
                item["expectedDate"],
            )

            report[
                "sequential"
            ].append(
                {
                    "group": "leave_date",
                    "message": (
                        item["message"]
                    ),
                    "baseState": (
                        base_leave_state
                    ),
                    "expectedDate": (
                        item[
                            "expectedDate"
                        ]
                    ),
                    "domainOk": domain_ok,
                    "dateOk": date_ok,
                    "passed": (
                        domain_ok
                        and date_ok
                    ),
                    "result": summary,
                }
            )

        except Exception:
            report[
                "sequential"
            ].append(
                {
                    "group": "leave_date",
                    "message": (
                        item["message"]
                    ),
                    "passed": False,
                    "exception": (
                        traceback.format_exc()
                    ),
                }
            )

    direct_passed = sum(
        1
        for item in report["direct"]
        if item.get("passed")
    )

    sequential_passed = sum(
        1
        for item in (
            report["sequential"]
        )
        if item.get("passed")
    )

    report["checks"] = {
        "directPassed": direct_passed,
        "directTotal": len(
            report["direct"]
        ),
        "sequentialPassed": (
            sequential_passed
        ),
        "sequentialTotal": len(
            report["sequential"]
        ),
    }

    return report


def run_guard_audit() -> dict[str, Any]:
    report: dict[str, Any] = {
        "importOk": False,
        "cases": [],
        "error": None,
    }

    try:
        module = import_current(
            "app.application.services.intent_guard"
        )

        guard_class = getattr(
            module,
            "IntentGuard",
        )

        guard = guard_class()

        report["importOk"] = True

    except Exception:
        report["error"] = (
            traceback.format_exc()
        )

        return report

    messages = [
        "8",
        "۸",
        "8 صبح",
        "8 شب",
        "8 و نیم",
        "8 و چهل و پنج دقیقه",
        "4 مرداد",
        "۴ مرداد",
        "فردا",
        "ثبت ترد برای فردا",
        "ثبت تردد برای فردا",
        (
            "میخوام مرخصی استحقاقی "
            "ثبت کنم برای فردا"
        ),
        "مرخصی اسحقاقی برای فردا",
        (
            "برای یکشنبه قیمه "
            "سیب زمینی رو حذف کن"
        ),
    ]

    for message in messages:
        try:
            decision = guard.analyze(
                message
            )

            report["cases"].append(
                {
                    "message": message,
                    "decision": safe_value(
                        decision
                    ),
                }
            )

        except Exception:
            report["cases"].append(
                {
                    "message": message,
                    "exception": (
                        traceback.format_exc()
                    ),
                }
            )

    return report


def run_text_parser_audit() -> dict[str, Any]:
    report: dict[str, Any] = {
        "importOk": False,
        "times": [],
        "dates": [],
        "error": None,
    }

    try:
        module = import_current(
            "app.domain.text"
        )

        extract_times = getattr(
            module,
            "extract_times",
        )

        extract_dates = getattr(
            module,
            "extract_jalali_dates",
        )

        normalize = getattr(
            module,
            "normalize_persian_text",
        )

        report["importOk"] = True

    except Exception:
        report["error"] = (
            traceback.format_exc()
        )

        return report

    time_messages = [
        "8",
        "۸",
        "8 صبح",
        "۸ صبح",
        "8 شب",
        "8 و نیم",
        "8 و نیم صبح",
        "8 و نیم شب",
        "8 و چهل و پنج دقیقه",
        (
            "8 و چهل و پنج دقیقه صبح"
        ),
        (
            "8 و چهل و پنج دقیقه شب"
        ),
        "10 و پنجاه دقیقه شب",
        "ساعت 8",
        "ساعت 08:30",
        "20:15",
    ]

    for message in time_messages:
        try:
            report["times"].append(
                {
                    "message": message,
                    "normalized": (
                        normalize(message)
                    ),
                    "result": safe_value(
                        extract_times(
                            message
                        )
                    ),
                }
            )

        except Exception:
            report["times"].append(
                {
                    "message": message,
                    "exception": (
                        traceback.format_exc()
                    ),
                }
            )

    date_messages = [
        "4 مرداد",
        "۴ مرداد",
        "چهارم مرداد",
        "1405/05/04",
        "۱۴۰۵/۰۵/۰۴",
        "فردا",
        "پس فردا",
        "یکشنبه",
    ]

    for message in date_messages:
        try:
            report["dates"].append(
                {
                    "message": message,
                    "normalized": (
                        normalize(message)
                    ),
                    "result": safe_value(
                        extract_dates(
                            message
                        )
                    ),
                }
            )

        except Exception:
            report["dates"].append(
                {
                    "message": message,
                    "exception": (
                        traceback.format_exc()
                    ),
                }
            )

    return report


def discover_backups() -> list[str]:
    results = []

    app_path = ROOT / "app"

    for path in app_path.rglob(
        "*.bak*"
    ):
        if path.is_file():
            results.append(
                str(path)
            )

    results.sort()

    return results


def make_text_report(
    report: dict[str, Any],
) -> str:
    lines = []

    lines.append(
        "DOMAIN / CONTEXT / DATE / TIME AUDIT"
    )

    lines.append(
        "=" * 72
    )

    lines.append(
        f"Generated: {report['generatedAt']}"
    )

    lines.append(
        f"Root: {report['root']}"
    )

    lines.append(
        f"Reference Jalali date: "
        f"{REFERENCE_DATE}"
    )

    lines.append("")

    lines.append(
        "TARGET BEHAVIOR"
    )

    lines.append("-" * 72)

    for item in report[
        "targetBehavior"
    ]:
        lines.append(
            f"- {item}"
        )

    lines.append("")

    lines.append(
        "SOURCE FILES"
    )

    lines.append("-" * 72)

    for item in report[
        "sourceFiles"
    ]:
        lines.append(
            (
                f"{item['relativePath']} | "
                f"syntax={item['syntax']['ok']} | "
                f"sha256={item['sha256']}"
            )
        )

    lines.append("")

    lines.append(
        "NLU TEST SUMMARY"
    )

    lines.append("-" * 72)

    nlu = report["runtime"]["nlu"]

    lines.append(
        json.dumps(
            nlu.get("checks"),
            ensure_ascii=False,
            indent=2,
        )
    )

    lines.append("")

    lines.append(
        "DIRECT NLU CASES"
    )

    lines.append("-" * 72)

    for item in nlu.get(
        "direct",
        [],
    ):
        lines.append(
            json.dumps(
                item,
                ensure_ascii=False,
                indent=2,
            )
        )

    lines.append("")

    lines.append(
        "SEQUENTIAL NLU CASES"
    )

    lines.append("-" * 72)

    for item in nlu.get(
        "sequential",
        [],
    ):
        lines.append(
            json.dumps(
                item,
                ensure_ascii=False,
                indent=2,
            )
        )

    lines.append("")

    lines.append(
        "INTENT GUARD CASES"
    )

    lines.append("-" * 72)

    lines.append(
        json.dumps(
            report["runtime"][
                "intentGuard"
            ],
            ensure_ascii=False,
            indent=2,
        )
    )

    lines.append("")

    lines.append(
        "LOW-LEVEL DATE/TIME PARSERS"
    )

    lines.append("-" * 72)

    lines.append(
        json.dumps(
            report["runtime"][
                "textParsers"
            ],
            ensure_ascii=False,
            indent=2,
        )
    )

    lines.append("")

    lines.append(
        "CONSTANTS AND PATCH MARKERS"
    )

    lines.append("-" * 72)

    lines.append(
        json.dumps(
            report["sourceAnalysis"],
            ensure_ascii=False,
            indent=2,
        )
    )

    lines.append("")

    lines.append(
        "SEARCH SNIPPETS"
    )

    lines.append("-" * 72)

    for item in report[
        "searchSnippets"
    ]:
        lines.append(
            (
                f"\nFILE: {item['file']}\n"
                f"TERM: {item['term']}\n"
                f"{item['snippet']}\n"
            )
        )

    return "\n".join(lines)


def create_zip(
    source_dir: Path,
    zip_path: Path,
) -> None:
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(
        zip_path,
        mode="w",
        compression=(
            zipfile.ZIP_DEFLATED
        ),
    ) as archive:
        for path in source_dir.rglob(
            "*"
        ):
            if not path.is_file():
                continue

            archive.write(
                path,
                arcname=str(
                    path.relative_to(
                        source_dir
                    )
                ),
            )


def main() -> None:
    if not ROOT.exists():
        raise FileNotFoundError(
            ROOT
        )

    existing_files = [
        path
        for path in SOURCE_FILES
        if path.exists()
    ]

    missing_files = [
        str(path)
        for path in SOURCE_FILES
        if not path.exists()
    ]

    if not existing_files:
        raise RuntimeError(
            "No source files found."
        )

    if OUTPUT_DIR.exists():
        shutil.rmtree(
            OUTPUT_DIR
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    sys.path.insert(
        0,
        str(ROOT),
    )

    source_files_report = []
    source_analysis = {}
    all_snippets = []

    for path in existing_files:
        text = path.read_text(
            encoding="utf-8-sig"
        )

        copied_path = copy_source(
            path
        )

        metadata = file_metadata(
            path
        )

        metadata["copiedPath"] = str(
            copied_path
        )

        metadata["syntax"] = (
            syntax_check(path)
        )

        source_files_report.append(
            metadata
        )

        source_analysis[
            str(
                path.relative_to(ROOT)
            )
        ] = {
            "constants": (
                source_constants(
                    text
                )
            ),
            "markers": (
                source_markers(
                    text
                )
            ),
            "functions": (
                function_ranges(
                    path,
                    text,
                )
            ),
            "totalLines": len(
                text.splitlines()
            ),
        }

        all_snippets.extend(
            search_snippets(
                path,
                text,
            )
        )

    report = {
        "generatedAt": (
            datetime.now().isoformat(
                timespec="seconds"
            )
        ),
        "root": str(ROOT),
        "referenceDate": (
            REFERENCE_DATE
        ),
        "targetBehavior": [
            (
                "Explicit domain in the new "
                "message overrides old domain state."
            ),
            (
                "Food, leave, mission and "
                "attendance slots never leak "
                "into each other."
            ),
            (
                "Conversation state remains active "
                "for exactly 3 minutes and refreshes "
                "only on related continuation."
            ),
            (
                "A short answer is resolved against "
                "the assistant's pending question "
                "before IntentGuard rejects it."
            ),
            (
                "A bare hour such as 8 asks whether "
                "the user means morning or night."
            ),
            (
                "8 morning, 8 night, 8:30, "
                "8 and forty-five minutes and "
                "Persian digits are understood."
            ),
            (
                "4 Mordad, Persian 4 Mordad, "
                "tomorrow, day after tomorrow and "
                "weekday expressions are understood "
                "inside the active domain."
            ),
            (
                "Common typos such as اسحقاقی، "
                "ترد and weekday misspellings "
                "are normalized before routing."
            ),
            (
                "Regression tests cover direct "
                "requests, domain switching and "
                "multi-turn continuations."
            ),
        ],
        "missingFiles": missing_files,
        "sourceFiles": (
            source_files_report
        ),
        "sourceAnalysis": (
            source_analysis
        ),
        "searchSnippets": (
            all_snippets
        ),
        "runtime": {
            "nlu": run_nlu_audit(),
            "intentGuard": (
                run_guard_audit()
            ),
            "textParsers": (
                run_text_parser_audit()
            ),
        },
        "backups": discover_backups(),
    }

    REPORT_JSON.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    REPORT_TEXT.write_text(
        make_text_report(
            report
        ),
        encoding="utf-8",
    )

    create_zip(
        OUTPUT_DIR,
        ZIP_PATH,
    )

    syntax_ok = all(
        item["syntax"]["ok"]
        for item in source_files_report
    )

    nlu_checks = (
        report["runtime"]
        ["nlu"]
        .get("checks")
        or {}
    )

    print("AUDIT_OK")
    print(
        f"SOURCE_SYNTAX_OK={syntax_ok}"
    )
    print(
        "NLU_DIRECT="
        f"{nlu_checks.get('directPassed', 0)}"
        "/"
        f"{nlu_checks.get('directTotal', 0)}"
    )
    print(
        "NLU_SEQUENTIAL="
        f"{nlu_checks.get('sequentialPassed', 0)}"
        "/"
        f"{nlu_checks.get('sequentialTotal', 0)}"
    )
    print(
        f"REPORT={REPORT_TEXT}"
    )
    print(
        f"BUNDLE={ZIP_PATH}"
    )


if __name__ == "__main__":
    try:
        main()

    except Exception:
        print("AUDIT_FAILED")
        traceback.print_exc()
        raise