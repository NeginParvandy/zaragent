from __future__ import annotations

import json
import logging
from typing import Any

from app.core.exceptions import AppError, ConflictError
from app.domain.models import AgentContext
from app.domain.text import (
    hours_between,
    normalize_persian_text,
    normalize_time,
    parse_bool,
    sap_duration_to_time,
    time_to_seconds,
    validate_jalali_range,
)
from app.infrastructure.clients.personnel_client import PersonnelClient


logger = logging.getLogger(__name__)

class HrService:
    def __init__(self, client: PersonnelClient):
        self.client = client

    async def get_time_account(self, context: AgentContext, date: str) -> dict[str, Any]:
        start, _ = validate_jalali_range(date, date)
        return await self.client.get("GetTimeAccount", context, {"EmployeeID": context.employee_id, "Date": start})

    async def get_leave_types(self, context: AgentContext) -> dict[str, Any]:
        return await self.client.get("GetLeaveType", context, {"EmployeeID": context.employee_id})

    async def get_quota_available(self, context: AgentContext, absence_type_code: str, info_type: str) -> dict[str, Any]:
        return await self.client.get(
            "GetLeaveQuotaAvailable",
            context,
            {"AbsenceTypeCode": absence_type_code, "EmployeeID": context.employee_id, "InfoType": info_type},
        )

    async def calculate_leave_span(
        self,
        context: AgentContext,
        absence_type_code: str,
        info_type: str,
        start_date: str,
        end_date: str,
        begin_time: str = "",
        end_time: str = "",
    ) -> dict[str, Any]:
        start_date, end_date = validate_jalali_range(start_date, end_date)
        params: dict[str, Any] = {
            "EmployeeID": context.employee_id,
            "AbsenceTypeCode": absence_type_code,
            "InfoType": info_type,
            "StartDate": start_date,
            "EndDate": end_date,
        }
        if begin_time:
            params["BeginTime"] = normalize_time(begin_time)
        if end_time:
            params["EndTime"] = normalize_time(end_time)
        return await self.client.get("GetCalculateLeaveSpan", context, params)

    async def get_leave_requests(self, context: AgentContext, start_date: str) -> dict[str, Any]:
        start_date, _ = validate_jalali_range(start_date, start_date)
        return await self.client.get("GetLeaveRequest", context, {"EmployeeID": context.employee_id, "StartDate": start_date})

    async def get_leave_request_detail(
        self, context: AgentContext, request_id: str, change_state_id: int | str, leave_key: str
    ) -> dict[str, Any]:
        return await self.client.get(
            "GetLeaveRequestDetail",
            context,
            {"EmployeeID": context.employee_id, "RequestID": request_id, "ChangeStateID": change_state_id, "LeaveKey": leave_key},
        )

    async def delete_leave_request(
        self,
        context: AgentContext,
        request_id: str,
        change_state_id: int | str,
        leave_key: str,
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if not request_id or not leave_key:
            raise AppError("شناسه درخواست برای حذف کامل نیست.", code="INVALID_DELETE_REQUEST")
        return await self.client.post_json(
            "LeaveRequestSetDelete",
            context,
            {"employeeID": context.employee_id, "requestID": request_id, "changeStateID": change_state_id, "leaveKey": leave_key},
            idempotency_key=idempotency_key,
        )

    async def save_leave(
        self,
        context: AgentContext,
        leave_type: dict[str, Any],
        *,
        start_date: str,
        end_date: str,
        start_time: str = "",
        end_time: str = "",
        notes: str = "",
        additional_values: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        start_date, end_date = validate_jalali_range(start_date, end_date)
        is_partial = parse_bool(leave_type.get("isAllowedDurationPartialDay"))
        allows_multiple_days = parse_bool(leave_type.get("isAllowedDurationMultipleDay"))
        if not allows_multiple_days and start_date != end_date:
            raise AppError("این نوع درخواست امکان ثبت چندروزه ندارد.", code="MULTI_DAY_NOT_ALLOWED")
        safe_start_time = normalize_time(start_time) if is_partial else ""
        safe_end_time = normalize_time(end_time) if is_partial else ""
        planned_hours = "0"
        if is_partial:
            if not safe_start_time or not safe_end_time:
                raise AppError("ساعت شروع و پایان برای درخواست ساعتی الزامی است.", code="TIME_REQUIRED")
            planned_hours = f"{hours_between(safe_start_time, safe_end_time):g}"
        self._validate_required_additional_fields(leave_type, additional_values or {})
        absence_code = str(leave_type.get("absenceTypeCode") or "")
        if not absence_code:
            raise AppError("کد نوع درخواست مشخص نیست.", code="ABSENCE_TYPE_REQUIRED")
        info_type = str(leave_type.get("infoType") or leave_type.get("infotype") or "")
        if info_type:
            span_result = await self.calculate_leave_span(
                context,
                absence_code,
                info_type,
                start_date,
                end_date,
                safe_start_time,
                safe_end_time,
            )

            logger.warning(
                (
                    "LEAVE_SPAN_RESULT employee_id=%s "
                    "absence_type_code=%s result=%r"
                ),
                context.employee_id,
                absence_code,
                span_result,
            )

            await self.get_quota_available(
                context,
                absence_code,
                info_type,
            )
        payload = {
            "StartDate": start_date,
            "EndDate": end_date,
            "StartTime": safe_start_time,
            "EndTime": safe_end_time,
            "EmployeeID": context.employee_id,
            "AbsenceTypeName": leave_type.get("absenceTypeName") or "",
            "AbsenceTypeCode": absence_code,
            "Notes": notes or "",
            "PlannedWorkingHours": planned_hours,
            "IsMultiLevelApproval": str(parse_bool(leave_type.get("isMultiLevelApproval"))).lower(),
            "IsAllowedDurationMultipleDay": str(allows_multiple_days).lower(),
            "ApproverLvlsJson": self.build_approver_lvls_json(leave_type),
            "AdditionalFieldsJson": self.build_additional_fields_json(leave_type, additional_values or {}),
        }
        return await self.client.post_form("PostLeaveSave", context, payload, idempotency_key=idempotency_key)

    async def get_time_events(self, context: AgentContext, begda: str, endda: str) -> dict[str, Any]:
        begda, endda = validate_jalali_range(begda, endda)
        return await self.client.get("GetTimeEvent", context, {"EmployeeID": context.employee_id, "Begda": begda, "Endda": endda})

    async def post_time_event(
        self,
        context: AgentContext,
        event_date: str,
        event_time: str,
        note: str = "",
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        event_date, _ = validate_jalali_range(event_date, event_date)
        event_time = normalize_time(event_time)
        return await self.client.post_json(
            "PostTimeEventSet",
            context,
            {"employeeID": context.employee_id, "eventDate": event_date, "eventTime": event_time, "note": note or ""},
            idempotency_key=idempotency_key,
        )

    async def ensure_no_exact_duplicate_leave(
        self,
        context: AgentContext,
        *,
        absence_type_code: str,
        start_date: str,
        end_date: str,
        start_time: str = "",
        end_time: str = "",
    ) -> None:
        response = await self.get_leave_requests(context, start_date)
        rows = response.get("data") or []
        if not isinstance(rows, list):
            return
        wanted_start, wanted_end = validate_jalali_range(start_date, end_date)
        wanted_start_time = normalize_time(start_time) if start_time else ""
        wanted_end_time = normalize_time(end_time) if end_time else ""
        for row in rows:
            if not isinstance(row, dict):
                continue
            row_code = str(row.get("absenceTypeCode") or row.get("AbsenceTypeCode") or "")
            row_start = str(row.get("startDate") or row.get("StartDate") or row.get("begda") or "")
            row_end = str(row.get("endDate") or row.get("EndDate") or row.get("endda") or row_start)
            try:
                row_start, row_end = validate_jalali_range(row_start, row_end)
            except ValueError:
                continue
            row_start_time = sap_duration_to_time(row.get("startTime") or row.get("StartTime") or row.get("beginTime"))
            row_end_time = sap_duration_to_time(row.get("endTime") or row.get("EndTime"))
            same_time = (not wanted_start_time and not wanted_end_time) or (
                row_start_time == wanted_start_time and row_end_time == wanted_end_time
            )
            if row_code == str(absence_type_code) and row_start == wanted_start and row_end == wanted_end and same_time:
                raise ConflictError(
                    "درخواست مشابه قبلاً ثبت شده است.",
                    details={"absenceTypeCode": absence_type_code, "startDate": wanted_start, "endDate": wanted_end},
                )

    def find_leave_type(self, leave_types: list[dict[str, Any]], text: str) -> dict[str, Any] | None:
        normalized = normalize_persian_text(text).lower()
        code_hits = [
            item for item in leave_types if str(item.get("absenceTypeCode") or "") and str(item.get("absenceTypeCode")) in normalized
        ]
        if code_hits:
            return code_hits[0]
        named_matches: list[tuple[int, dict[str, Any]]] = []
        for item in leave_types:
            name = normalize_persian_text(str(item.get("absenceTypeName") or item.get("name") or "")).lower()
            if name and name in normalized:
                named_matches.append((len(name), item))
        if named_matches:
            return max(named_matches, key=lambda pair: pair[0])[1]
        rules = [
            (["ماموریت ساعتی", "مأموریت ساعتی"], "1003"),
            (["ماموریت خارج", "مأموریت خارج"], "1002"),
            (["اضافه کاری", "اضافه‌کاری"], "1004"),
            (["مرخصی ساعتی"], "0080"),
            (["استعلاجی", "پزشکی"], "0020"),
            (["استحقاقی", "مرخصی روزانه"], "0010"),
            (["فوت", "معذوریت"], "0030"),
            (["ماموریت", "مأموریت"], "1000"),
            (["ساعتی"], "0080"),
            (["روزانه"], "0010"),
        ]
        for keywords, code in rules:
            if any(normalize_persian_text(keyword).lower() in normalized for keyword in keywords):
                return next((item for item in leave_types if str(item.get("absenceTypeCode") or "") == code), None)
        return None

    def validate_time_event_distance(self, rows: list[dict[str, Any]], new_time: str) -> tuple[bool, str | None]:
        wanted = time_to_seconds(new_time)
        if wanted is None:
            raise AppError("ساعت تردد نامعتبر است.", code="INVALID_TIME")
        for row in rows:
            existing_text = sap_duration_to_time(row.get("eventTime"))
            existing = time_to_seconds(existing_text)
            if existing is not None and abs(wanted - existing) < 60:
                return False, existing_text
        return True, None

    def build_approver_lvls_json(self, leave_type: dict[str, Any]) -> str:
        results = (leave_type.get("toApprover") or {}).get("results") or leave_type.get("approvers") or []
        items = [
            {
                "Name": row.get("name") or row.get("Name") or row.get("employeeName") or row.get("approverEmployeeName") or "",
                "Pernr": row.get("pernr") or row.get("Pernr") or row.get("employeeID") or row.get("approverEmployeeID") or "",
                "Seqnr": row.get("seqnr") or row.get("Seqnr") or row.get("sequence") or "",
                "DefaultFlag": parse_bool(row.get("defaultFlag", row.get("DefaultFlag"))),
            }
            for row in results
            if isinstance(row, dict)
        ]
        return json.dumps(items, ensure_ascii=False)

    def build_additional_fields_json(self, leave_type: dict[str, Any], values: dict[str, Any]) -> str:
        definitions = (leave_type.get("toAdditionalFieldsDefinition") or {}).get("results") or []
        result: dict[str, Any] = {}
        for item in definitions:
            key = item.get("fieldName") or item.get("fieldname") or item.get("name") or item.get("field")
            if key:
                result[str(key)] = values.get(str(key), "")
        return json.dumps(result, ensure_ascii=False)

    def _validate_required_additional_fields(self, leave_type: dict[str, Any], values: dict[str, Any]) -> None:
        definitions = (leave_type.get("toAdditionalFieldsDefinition") or {}).get("results") or []
        missing: list[str] = []
        for item in definitions:
            key = item.get("fieldName") or item.get("fieldname") or item.get("name") or item.get("field")
            required = parse_bool(item.get("isRequired", item.get("required")))
            if key and required and not str(values.get(str(key), "")).strip():
                missing.append(str(item.get("fieldLabel") or item.get("label") or key))
        if missing:
            raise AppError("فیلدهای تکمیلی الزامی وارد نشده‌اند.", code="MISSING_ADDITIONAL_FIELDS", details={"fields": missing})
