from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

from app.domain.text import (
    normalize_jalali_date,
    normalize_persian_text,
)

T = TypeVar("T")


class ApiErrorBody(BaseModel):
    code: str
    details: Any = None


class ApiResponse(BaseModel, Generic[T]):
    hasError: bool = False
    data: T | None = None
    message: str = ""
    error: ApiErrorBody | None = None


class Severity(str, Enum):
    info = "info"
    warning = "warning"
    danger = "danger"
    success = "success"


class ModuleName(str, Enum):
    food = "food"
    leave = "leave"
    attendance = "attendance"
    general = "general"


class ActionType(str, Enum):
    reserve_food = "RESERVE_FOOD"
    cancel_food = "CANCEL_FOOD"
    rate_food = "RATE_FOOD"
    create_leave = "CREATE_LEAVE"
    delete_leave = "DELETE_LEAVE"
    create_time_event = "CREATE_TIME_EVENT"
    dismiss = "DISMISS"
    open_page = "OPEN_PAGE"


class UserSession(BaseModel):
    """
    اطلاعات نشست سرویس‌های Food و HR.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
    )

    authorization_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "authorizationToken",
            "accessToken",
            "authToken",
            "token",
            "Authorization",
        ),
    )

    username_hash: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "usernameHash",
            "UsernameHash",
        ),
    )

    password_hash: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "passwordHash",
            "PasswordHash",
        ),
    )

    digit_code: int | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "digitCode",
            "DigitCode",
        ),
        ge=0,
    )

    @field_validator("digit_code", mode="before")
    @classmethod
    def validate_digit_code(
        cls,
        value: Any,
    ) -> Any:
        if value in (None, ""):
            return None

        if isinstance(value, bool):
            raise ValueError(
                "digitCode must be numeric"
            )

        try:
            return int(
                normalize_persian_text(
                    str(value)
                )
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "digitCode must be numeric"
            ) from exc


class AgentContext(BaseModel):
    """
    مدل داخلی Context.

    این مدل مستقیماً Request Body هیچ Endpointی نیست.
    بنابراین فیلدهای داخلی آن در Swagger عمومی نمایش
    داده نمی‌شوند.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
    )

    employee_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "employeeId",
            "EmployeeID",
            "employeeID",
        ),
        min_length=1,
        max_length=30,
    )

    # فقط برای سازگاری داخلی Chat نگه داشته شده است.
    # در مدل عمومی Chat وجود ندارد و در Swagger دیده نمی‌شود.
    display_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "displayName",
            "fullName",
            "name",
        ),
        max_length=200,
    )

    conversation_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "conversationId",
            "conversation_id",
        ),
        min_length=1,
        max_length=100,
    )

    date: str | None = None

    restaurant_id: int | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "restaurantId",
            "resturantId",
        ),
        ge=1,
    )

    meal_id: int | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "mealId",
        ),
        ge=1,
    )

    session: UserSession | None = None

    # تنظیمات داخلی Reminder.
    # از هیچ Request عمومی دریافت نمی‌شوند.
    is_month_end_reminder: bool = False
    reminder_scope: str | None = None

    @field_validator(
        "employee_id",
        "display_name",
        "conversation_id",
        "reminder_scope",
        mode="before",
    )
    @classmethod
    def strip_optional_text(
        cls,
        value: Any,
    ) -> Any:
        if value is None:
            return None

        text = str(value).strip()
        return text or None

    @field_validator("date")
    @classmethod
    def validate_date(
        cls,
        value: str | None,
    ) -> str | None:
        if not value:
            return None

        return normalize_jalali_date(value)


class EmployeeRequestBase(BaseModel):
    """
    مدل پایه Endpointهایی که فقط شناسه کاربر
    را نیاز دارند.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
    )

    employee_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "employeeId",
            "EmployeeID",
            "employeeID",
        ),
        min_length=1,
        max_length=30,
    )

    @field_validator(
        "employee_id",
        mode="before",
    )
    @classmethod
    def strip_employee_id(
        cls,
        value: Any,
    ) -> Any:
        if value is None:
            return None

        text = str(value).strip()
        return text or None

    def to_context(
        self,
        **overrides: Any,
    ) -> AgentContext:
        data: dict[str, Any] = {
            "employee_id": self.employee_id,
        }

        data.update(overrides)

        return AgentContext(**data)


class IntegrationContextRequest(EmployeeRequestBase):
    """
    فیلدهای مشترک Endpointهایی که به HR یا Food
    متصل می‌شوند.
    """

    date: str | None = None

    restaurant_id: int | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "restaurantId",
            "resturantId",
        ),
        ge=1,
    )

    meal_id: int | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "mealId",
        ),
        ge=1,
    )

    session: UserSession | None = None

    @field_validator("date")
    @classmethod
    def validate_date(
        cls,
        value: str | None,
    ) -> str | None:
        if not value:
            return None

        return normalize_jalali_date(value)

    def to_context(
        self,
        **overrides: Any,
    ) -> AgentContext:
        data: dict[str, Any] = {
            "employee_id": self.employee_id,
            "date": self.date,
            "restaurant_id": self.restaurant_id,
            "meal_id": self.meal_id,
            "session": self.session,
        }

        data.update(overrides)

        return AgentContext(**data)


class ChatContextRequest(EmployeeRequestBase):
    """Public context accepted by the Chat API."""

    conversation_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "conversationId",
            "conversation_id",
        ),
        min_length=1,
        max_length=100,
    )

    # PUBLIC_CHAT_DATE_REMOVED_SAFE
    session: UserSession | None = Field(
        default=None
    )

    def to_context(self) -> AgentContext:
        return AgentContext(
            employee_id=self.employee_id,
            conversation_id=self.conversation_id,
            session=self.session,
        )


class DailyBriefRequest(IntegrationContextRequest):
    """
    Request مخصوص POST /api/agent/daily-brief.
    """

    pass


class ReminderCheckRequest(IntegrationContextRequest):
    """
    Request مخصوص POST /api/agent/reminders/check.

    تشخیص پایان ماه و تنظیمات مربوط به آن کاملاً
    داخلی است.
    """

    pass


class ReminderListRequest(EmployeeRequestBase):
    """
    Request مخصوص POST /api/agent/reminders.

    وضعیت Reminder داخلی است و مصرف‌کننده API
    نیازی به ارسال status ندارد.
    """

    pass


class ChatRequest(BaseModel):
    """
    Main Agent Chat request.

    Supports both:
    1. New contract with context.session
    2. Legacy application contract with session fields at root level
    """

    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
    )

    message: str = Field(
        min_length=1,
        max_length=2000,
    )

    conversation_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "conversationId",
            "conversation_id",
        ),
        min_length=1,
        max_length=100,
    )

    context: ChatContextRequest | None = None

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_session_fields(
        cls,
        value: Any,
    ) -> Any:
        if not isinstance(value, dict):
            return value

        data = dict(value)

        legacy_keys = (
            "authorizationToken",
            "accessToken",
            "authToken",
            "token",
            "Authorization",
            "usernameHash",
            "UsernameHash",
            "passwordHash",
            "PasswordHash",
            "digitCode",
            "DigitCode",
        )

        legacy_data = {
            key: data[key]
            for key in legacy_keys
            if key in data
            and data[key] not in (None, "")
        }

        if not legacy_data:
            return data

        legacy_session = UserSession.model_validate(
            legacy_data
        )

        raw_context = data.get("context")

        if raw_context is None:
            context_data: dict[str, Any] = {}

        elif isinstance(
            raw_context,
            ChatContextRequest,
        ):
            context_data = raw_context.model_dump()

        elif isinstance(
            raw_context,
            BaseModel,
        ):
            context_data = raw_context.model_dump()

        elif isinstance(raw_context, dict):
            context_data = dict(raw_context)

        else:
            return data

        raw_session = context_data.get("session")

        if raw_session is None:
            merged_session = legacy_session

        else:
            existing_session = (
                raw_session
                if isinstance(
                    raw_session,
                    UserSession,
                )
                else UserSession.model_validate(
                    raw_session
                )
            )

            merged_session = existing_session.model_copy(
                update={
                    "authorization_token": (
                        existing_session.authorization_token
                        if existing_session.authorization_token
                        is not None
                        else legacy_session.authorization_token
                    ),
                    "username_hash": (
                        existing_session.username_hash
                        if existing_session.username_hash
                        is not None
                        else legacy_session.username_hash
                    ),
                    "password_hash": (
                        existing_session.password_hash
                        if existing_session.password_hash
                        is not None
                        else legacy_session.password_hash
                    ),
                    "digit_code": (
                        existing_session.digit_code
                        if existing_session.digit_code
                        is not None
                        else legacy_session.digit_code
                    ),
                }
            )

        context_data["session"] = merged_session
        data["context"] = context_data

        return data

    @field_validator("message")
    @classmethod
    def message_not_empty(
        cls,
        value: str,
    ) -> str:
        value = (value or "").strip()

        if not value:
            raise ValueError(
                "message is required"
            )

        return value


class ActionRequestBase(EmployeeRequestBase):
    """
    مدل پایه عملیات Pending Action.
    """

    action_id: str = Field(
        validation_alias=AliasChoices(
            "actionId",
            "id",
        ),
        min_length=8,
        max_length=64,
    )


class ConfirmActionRequest(ActionRequestBase):
    """
    Confirm برای اجرای عملیات واقعی به Session
    نیاز دارد.
    """

    session: UserSession | None = None


class CancelActionRequest(ActionRequestBase):
    """
    Cancel فقط actionId و employeeId نیاز دارد.
    """

    pass


class ActionStatusRequest(ActionRequestBase):
    """
    Status فقط actionId و employeeId نیاز دارد.
    """

    pass


class PendingActionRecord(BaseModel):
    id: str
    employee_id: str
    action_type: str
    payload: dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None
    idempotency_key: str
    reminder_id: str | None = None


class ReminderRecord(BaseModel):
    id: str
    employee_id: str
    module: str
    reminder_type: str
    target_date: str | None
    title: str
    message: str
    severity: str = "info"

    actions: list[dict[str, Any]] = Field(
        default_factory=list,
    )

    status: str = "pending"
    created_at: datetime
    shown_at: datetime | None = None
    acted_at: datetime | None = None

    data: dict[str, Any] = Field(
        default_factory=dict,
    )

    action_id: str | None = None