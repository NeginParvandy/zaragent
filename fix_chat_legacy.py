from pathlib import Path


path = Path(r"D:\serviceAi\app\domain\models.py")
text = path.read_text(encoding="utf-8")


# Add model_validator to Pydantic imports.
if "    model_validator,\n" not in text:
    old_import = "    field_validator,\n)"
    new_import = "    field_validator,\n    model_validator,\n)"

    if old_import not in text:
        raise SystemExit("IMPORT_BLOCK_NOT_FOUND")

    text = text.replace(
        old_import,
        new_import,
        1,
    )


start_marker = "class ChatRequest(BaseModel):"
end_marker = "\n\nclass ActionRequestBase"

start = text.find(start_marker)

if start == -1:
    raise SystemExit("CHAT_REQUEST_START_NOT_FOUND")

end = text.find(
    end_marker,
    start,
)

if end == -1:
    raise SystemExit("CHAT_REQUEST_END_NOT_FOUND")


new_chat_request = '''class ChatRequest(BaseModel):
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
'''


updated = (
    text[:start]
    + new_chat_request
    + text[end:]
)

path.write_text(
    updated,
    encoding="utf-8",
)

print("PATCH_OK")
print(f"UPDATED_FILE={path}")