from __future__ import annotations

import ast
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(r"D:\serviceAi")
APP_DIR = ROOT_DIR / "app"

JSON_REPORT = ROOT_DIR / "nlu_architecture_report.json"
TEXT_REPORT = ROOT_DIR / "nlu_architecture_report.txt"


IMPORTANT_FILES = [
    APP_DIR / "application" / "services" / "chat_service.py",
    APP_DIR / "application" / "services" / "intent_guard.py",
    APP_DIR / "application" / "services" / "food_service.py",
    APP_DIR / "application" / "services" / "hr_service.py",
    APP_DIR / "domain" / "models.py",
    APP_DIR / "domain" / "text.py",
    APP_DIR / "api" / "routes" / "agent.py",
]


NLU_TERMS = {
    "intent",
    "normalize",
    "persian",
    "message",
    "chat",
    "date",
    "time",
    "hour",
    "minute",
    "today",
    "tomorrow",
    "yesterday",
    "food",
    "reserve",
    "restaurant",
    "leave",
    "mission",
    "attendance",
    "time_event",
    "confirmation",
    "pending",
    "history",
    "recommend",
    "rating",
    "parse",
    "extract",
    "regex",
    "pattern",
    "confidence",
    "domain",
    "entity",
    "employee",
    "action",
}


PERSIAN_BUSINESS_TERMS = {
    "غذا",
    "رزرو",
    "رستوران",
    "منو",
    "مرخصی",
    "ماموریت",
    "مأموریت",
    "تردد",
    "ورود",
    "خروج",
    "امروز",
    "فردا",
    "دیروز",
    "هفته",
    "ساعت",
    "تاریخ",
    "تأیید",
    "تایید",
    "لغو",
    "پیشنهاد",
    "امتیاز",
    "تاریخچه",
    "سوابق",
}


SKIP_PARTS = {
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    "backup",
    "backups",
}


SKIP_NAME_MARKERS = {
    ".bak",
    "_backup",
    "backup_",
    "_broken",
}


def normalize_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT_DIR))
    except ValueError:
        return str(path)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)

    return digest.hexdigest()


def should_skip(path: Path) -> bool:
    lowered_parts = {
        part.lower()
        for part in path.parts
    }

    if lowered_parts.intersection(SKIP_PARTS):
        return True

    lowered_name = path.name.lower()

    return any(
        marker in lowered_name
        for marker in SKIP_NAME_MARKERS
    )


def get_call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id

    if isinstance(node, ast.Attribute):
        parent = get_call_name(node.value)

        if parent:
            return f"{parent}.{node.attr}"

        return node.attr

    return ""


def get_string_value(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value

    return None


def has_relevant_term(value: str) -> bool:
    lowered = value.lower()

    if any(term in lowered for term in NLU_TERMS):
        return True

    return any(
        term in value
        for term in PERSIAN_BUSINESS_TERMS
    )


class PythonInspector(ast.NodeVisitor):
    def __init__(
        self,
        *,
        path: Path,
        source_lines: list[str],
    ):
        self.path = path
        self.source_lines = source_lines

        self.classes: list[dict[str, Any]] = []
        self.functions: list[dict[str, Any]] = []
        self.imports: list[str] = []
        self.calls: Counter[str] = Counter()
        self.regex_patterns: list[dict[str, Any]] = []
        self.relevant_strings: list[dict[str, Any]] = []
        self.class_fields: dict[str, list[str]] = defaultdict(list)

        self.current_class: str | None = None
        self.current_function: str | None = None

    def visit_Import(self, node: ast.Import) -> Any:
        for alias in node.names:
            self.imports.append(alias.name)

        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        module = node.module or ""

        imported = ", ".join(
            alias.name
            for alias in node.names
        )

        self.imports.append(
            f"{module}: {imported}"
        )

        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        previous_class = self.current_class
        self.current_class = node.name

        bases = [
            get_call_name(base)
            for base in node.bases
        ]

        methods = [
            child.name
            for child in node.body
            if isinstance(
                child,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            )
        ]

        self.classes.append(
            {
                "name": node.name,
                "line": node.lineno,
                "bases": bases,
                "methods": methods,
            }
        )

        for child in node.body:
            if isinstance(child, ast.AnnAssign):
                if isinstance(child.target, ast.Name):
                    self.class_fields[node.name].append(
                        child.target.id
                    )

            elif isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Name):
                        self.class_fields[node.name].append(
                            target.id
                        )

        self.generic_visit(node)
        self.current_class = previous_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self._visit_function(node)

    def visit_AsyncFunctionDef(
        self,
        node: ast.AsyncFunctionDef,
    ) -> Any:
        self._visit_function(node)

    def _visit_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        previous_function = self.current_function
        self.current_function = node.name

        arguments = [
            argument.arg
            for argument in node.args.args
        ]

        self.functions.append(
            {
                "name": node.name,
                "line": node.lineno,
                "class": self.current_class,
                "async": isinstance(
                    node,
                    ast.AsyncFunctionDef,
                ),
                "arguments": arguments,
                "relevant": has_relevant_term(
                    node.name
                ),
            }
        )

        self.generic_visit(node)
        self.current_function = previous_function

    def visit_Call(self, node: ast.Call) -> Any:
        call_name = get_call_name(node.func)

        if call_name:
            self.calls[call_name] += 1

        regex_calls = {
            "re.compile",
            "re.search",
            "re.match",
            "re.fullmatch",
            "re.findall",
            "re.finditer",
            "re.sub",
        }

        if call_name in regex_calls and node.args:
            pattern = get_string_value(node.args[0])

            if pattern is not None:
                self.regex_patterns.append(
                    {
                        "call": call_name,
                        "pattern": pattern,
                        "line": node.lineno,
                        "function": self.current_function,
                        "class": self.current_class,
                    }
                )

        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> Any:
        if isinstance(node.value, str):
            value = node.value.strip()

            if value and has_relevant_term(value):
                preview = value

                if len(preview) > 250:
                    preview = preview[:247] + "..."

                self.relevant_strings.append(
                    {
                        "line": getattr(
                            node,
                            "lineno",
                            None,
                        ),
                        "value": preview,
                        "function": self.current_function,
                        "class": self.current_class,
                    }
                )

        self.generic_visit(node)


def inspect_python_file(path: Path) -> dict[str, Any]:
    relative_path = normalize_path(path)

    result: dict[str, Any] = {
        "path": relative_path,
        "sizeBytes": path.stat().st_size,
        "sha256": file_hash(path),
        "syntaxValid": False,
        "syntaxError": None,
        "imports": [],
        "classes": [],
        "classFields": {},
        "functions": [],
        "calls": {},
        "regexPatterns": [],
        "relevantStrings": [],
        "matchingLines": [],
    }

    try:
        source = path.read_text(
            encoding="utf-8",
        )
    except UnicodeDecodeError:
        source = path.read_text(
            encoding="utf-8-sig",
        )

    source_lines = source.splitlines()

    try:
        tree = ast.parse(
            source,
            filename=str(path),
        )

        result["syntaxValid"] = True

    except SyntaxError as exc:
        result["syntaxError"] = {
            "relevantStrings": [],
        "matchingLines": [],
    }

    try:
        source = path.read_text(
            encoding="utf-8",
        )
    except UnicodeDecodeError:
        source = path.read_text(
            encoding="utf-8-sig",
        )

    source_lines = source.splitlines()

    try:
        tree = ast.parse(
            source,
            filename=str(path),
        )

        result["syntaxValid"] = True

    except SyntaxError as exc:
        result["syntaxError"] = {
            "message": str(exc),
            "line": exc.lineno,
            "offset": exc.offset,
        }

        return result

    inspector = PythonInspector(
        path=path,
        source_lines=source_lines,
    )

    inspector.visit(tree)

    result["imports"] = sorted(
        set(inspector.imports)
    )

    result["classes"] = inspector.classes
    result["classFields"] = dict(
        inspector.class_fields
    )

    result["functions"] = inspector.functions
    result["calls"] = dict(
        inspector.calls.most_common()
    )

    result["regexPatterns"] = (
        inspector.regex_patterns
    )

    result["relevantStrings"] = (
        inspector.relevant_strings
    )

    matching_lines: list[dict[str, Any]] = []

    for line_number, line in enumerate(
        source_lines,
        start=1,
    ):
        stripped = line.strip()

        if not stripped:
            continue

        if has_relevant_term(stripped):
            preview = stripped

            if len(preview) > 300:
                preview = preview[:297] + "..."

            matching_lines.append(
                {
                    "line": line_number,
                    "text": preview,
                }
            )

    result["matchingLines"] = (
        matching_lines[:500]
    )

    return result


def collect_python_files() -> list[Path]:
    files: list[Path] = []

    for path in APP_DIR.rglob("*.py"):
        if should_skip(path):
            continue

        files.append(path)

    return sorted(files)


def find_duplicate_function_names(
    file_reports: list[dict[str, Any]],
) -> dict[str, list[str]]:
    locations: dict[str, list[str]] = defaultdict(list)

    for report in file_reports:
        for function in report.get(
            "functions",
            [],
        ):
            name = function["name"]

            if not function.get("relevant"):
                continue

            location = (
                f"{report['path']}:{function['line']}"
            )

            locations[name].append(location)

    return {
        name: paths
        for name, paths in locations.items()
        if len(paths) > 1
    }


def extract_chat_model_summary(
    file_reports: list[dict[str, Any]],
) -> dict[str, Any]:
    for report in file_reports:
        if report["path"].replace(
            "\\",
            "/",
        ).endswith("app/domain/models.py"):
            class_fields = report.get(
                "classFields",
                {},
            )

            return {
                "ChatContextRequest": class_fields.get(
                    "ChatContextRequest",
                    [],
                ),
                "ChatRequest": class_fields.get(
                    "ChatRequest",
                    [],
                ),
                "AgentContext": class_fields.get(
                    "AgentContext",
                    [],
                ),
                "DailyBriefRequest": class_fields.get(
                    "DailyBriefRequest",
                    [],
                ),
            }

    return {}


def extract_nlu_components(
    file_reports: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []

    for report in file_reports:
        relevant_functions = [
            function
            for function in report.get(
                "functions",
                [],
            )
            if function.get("relevant")
        ]

        relevant_classes = [
            item
            for item in report.get(
                "classes",
                [],
            )
            if has_relevant_term(
                item["name"]
            )
        ]

        if (
            relevant_functions
            or relevant_classes
            or report.get("regexPatterns")
        ):
            components.append(
                {
                    "path": report["path"],
                    "classes": relevant_classes,
                    "functions": relevant_functions,
                    "regexCount": len(
                        report.get(
                            "regexPatterns",
                            [],
                        )
                    ),
                }
            )

    return components


def build_text_report(
    report: dict[str, Any],
) -> str:
    lines: list[str] = []

    lines.append(
        "Holding Smart Agent - NLU Architecture Report"
    )
    lines.append("=" * 72)
    lines.append(
        f"Generated at: {report['generatedAt']}"
    )
    lines.append(
        f"Root directory: {report['rootDirectory']}"
    )
    lines.append(
        f"Python files inspected: {report['summary']['pythonFileCount']}"
    )
    lines.append(
        f"Files with syntax errors: {report['summary']['syntaxErrorCount']}"
    )
    lines.append("")

    lines.append("Important files")
    lines.append("-" * 72)

    for item in report["importantFiles"]:
        status = "FOUND" if item["exists"] else "MISSING"

        lines.append(
            f"[{status}] {item['path']}"
        )

    lines.append("")
    lines.append("Public and internal request models")
    lines.append("-" * 72)

    model_summary = report.get(
        "chatModelSummary",
        {},
    )

    for class_name, fields in model_summary.items():
        joined_fields = ", ".join(fields) or "(none)"

        lines.append(
            f"{class_name}: {joined_fields}"
        )

    lines.append("")
    lines.append("Detected NLU components")
    lines.append("-" * 72)

    for component in report["nluComponents"]:
        lines.append(component["path"])

        for class_info in component["classes"]:
            lines.append(
                f"  CLASS {class_info['name']} "
                f"(line {class_info['line']})"
            )

        for function in component["functions"]:
            class_prefix = (
                f"{function['class']}."
                if function.get("class")
                else ""
            )

            lines.append(
                f"  FUNCTION {class_prefix}"
                f"{function['name']} "
                f"(line {function['line']})"
            )

        if component["regexCount"]:
            lines.append(
                f"  REGEX PATTERNS: "
                f"{component['regexCount']}"
            )

    lines.append("")
    lines.append("Duplicate relevant function names")
    lines.append("-" * 72)

    duplicates = report.get(
        "duplicateRelevantFunctions",
        {},
    )

    if not duplicates:
        lines.append("No duplicate relevant function names found.")
    else:
        for name, locations in sorted(
            duplicates.items()
        ):
            lines.append(name)

            for location in locations:
                lines.append(
                    f"  - {location}"
                )

    lines.append("")
    lines.append("Syntax errors")
    lines.append("-" * 72)

    syntax_errors = report.get(
        "syntaxErrors",
        [],
    )

    if not syntax_errors:
        lines.append("No syntax errors found.")
    else:
        for error in syntax_errors:
            lines.append(
                f"{error['path']}: "
                f"{error['error']}"
            )

    lines.append("")
    lines.append("Recommended review order")
    lines.append("-" * 72)
    lines.extend(
        [
            "1. app/application/services/chat_service.py",
            "2. app/application/services/intent_guard.py",
            "3. app/domain/text.py",
            "4. Date/time/entity extraction functions",
            "5. Pending confirmation routing",
            "6. Food, leave, mission and attendance handlers",
            "7. API route and request/response models",
        ]
    )

    lines.append("")
    lines.append(
        "This report only inspected source code. "
        "No project file was modified."
    )

    return "\n".join(lines)


def main() -> None:
    if not APP_DIR.exists():
        print(
            f"FAILED: App directory was not found: {APP_DIR}"
        )
        sys.exit(1)

    python_files = collect_python_files()

    file_reports: list[dict[str, Any]] = []

    for index, path in enumerate(
        python_files,
        start=1,
    ):
        print(
            f"[{index}/{len(python_files)}] "
            f"Inspecting {normalize_path(path)}"
        )

        file_reports.append(
            inspect_python_file(path)
        )

    syntax_errors = [
        {
            "path": item["path"],
            "error": item["syntaxError"],
        }
        for item in file_reports
        if not item["syntaxValid"]
    ]

    important_files = [
        {
            "path": normalize_path(path),
            "exists": path.exists(),
            "sha256": (
                file_hash(path)
                if path.exists()
                else None
            ),
        }
        for path in IMPORTANT_FILES
    ]

    report: dict[str, Any] = {
        "generatedAt": datetime.now().isoformat(
            timespec="seconds"
        ),
        "rootDirectory": str(ROOT_DIR),
        "summary": {
            "pythonFileCount": len(
                python_files
            ),
            "syntaxErrorCount": len(
                syntax_errors
            ),
            "importantFileCount": len(
                IMPORTANT_FILES
            ),
        },
        "importantFiles": important_files,
        "chatModelSummary": (
            extract_chat_model_summary(
                file_reports
            )
        ),
        "nluComponents": extract_nlu_components(
            file_reports
        ),
        "duplicateRelevantFunctions": (
            find_duplicate_function_names(
                file_reports
            )
        ),
        "syntaxErrors": syntax_errors,
        "files": file_reports,
    }

    JSON_REPORT.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    text_report = build_text_report(
        report
    )

    TEXT_REPORT.write_text(
        text_report,
        encoding="utf-8",
    )

    print("")
    print("SUCCESS")
    print(
        f"JSON report: {JSON_REPORT}"
    )
    print(
        f"Text report: {TEXT_REPORT}"
    )
    print(
        "No project source file was modified."
    )


if __name__ == "__main__":
    main()