from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    app_name: str = Field(default="Holding Smart Agent", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_debug: bool = Field(default=False, alias="APP_DEBUG")
    app_timezone: str = Field(default="Asia/Tehran", alias="APP_TIMEZONE")
    app_version: str = Field(default="2.4.6", alias="APP_VERSION")
    enable_docs: bool = Field(default=True, alias="ENABLE_DOCS")

    host: str = Field(default="127.0.0.1", alias="HOST")
    port: int = Field(default=8000, alias="PORT", ge=1, le=65535)
    allowed_hosts: str = Field(default="127.0.0.1,localhost,testserver", alias="ALLOWED_HOSTS")
    force_https: bool = Field(default=False, alias="FORCE_HTTPS")
    forwarded_allow_ips: str = Field(default="127.0.0.1", alias="FORWARDED_ALLOW_IPS")

    auth_required: bool = Field(default=False, alias="AUTH_REQUIRED")
    agent_api_key: SecretStr = Field(default=SecretStr(""), alias="AGENT_API_KEY")
    admin_api_key: SecretStr = Field(default=SecretStr(""), alias="ADMIN_API_KEY")
    enable_admin_endpoints: bool = Field(default=False, alias="ENABLE_ADMIN_ENDPOINTS")
    trusted_gateway_header: str = Field(default="X-Employee-Id", alias="TRUSTED_GATEWAY_HEADER")

    hr_api_base_url: str = Field(default="https://var-prd-test3.zarholding.com:4433", alias="HR_API_BASE_URL")
    food_api_base_url: str = Field(default="https://var-prd-test3.zarholding.com:4433", alias="FOOD_API_BASE_URL")
    api_version: str = Field(default="1", alias="API_VERSION")
    request_timeout_seconds: float = Field(default=15, alias="REQUEST_TIMEOUT_SECONDS", gt=0, le=120)
    connect_timeout_seconds: float = Field(default=5, alias="CONNECT_TIMEOUT_SECONDS", gt=0, le=60)
    use_case_timeout_seconds: float = Field(default=45, alias="USE_CASE_TIMEOUT_SECONDS", gt=1, le=300)
    verify_ssl: bool = Field(default=True, alias="VERIFY_SSL")
    internal_ca_bundle: str = Field(default="", alias="INTERNAL_CA_BUNDLE")
    external_get_retries: int = Field(default=2, alias="EXTERNAL_GET_RETRIES", ge=0, le=5)
    retry_backoff_seconds: float = Field(default=0.25, alias="RETRY_BACKOFF_SECONDS", ge=0, le=5)
    circuit_failure_threshold: int = Field(default=5, alias="CIRCUIT_FAILURE_THRESHOLD", ge=1, le=50)
    circuit_reset_seconds: int = Field(default=30, alias="CIRCUIT_RESET_SECONDS", ge=1, le=600)

    default_employee_id: str = Field(default="", alias="DEFAULT_EMPLOYEE_ID")
    default_auth_token: SecretStr = Field(default=SecretStr(""), alias="DEFAULT_AUTH_TOKEN")
    default_username_hash: SecretStr = Field(default=SecretStr(""), alias="DEFAULT_USERNAME_HASH")
    default_password_hash: SecretStr = Field(default=SecretStr(""), alias="DEFAULT_PASSWORD_HASH")
    default_digit_code: int | None = Field(default=None, alias="DEFAULT_DIGIT_CODE", ge=0)

    default_restaurant_id: int | None = Field(default=84, alias="DEFAULT_RESTAURANT_ID", ge=1)
    default_meal_id: int | None = Field(default=1, alias="DEFAULT_MEAL_ID", ge=1)
    max_rating_lookups: int = Field(default=6, alias="MAX_RATING_LOOKUPS", ge=0, le=20)
    rating_lookup_concurrency: int = Field(default=3, alias="RATING_LOOKUP_CONCURRENCY", ge=1, le=10)
    low_capacity_threshold: int = Field(default=5, alias="LOW_CAPACITY_THRESHOLD", ge=0)

    sqlite_path: str = Field(default="data/agent_state.db", alias="SQLITE_PATH")
    sqlite_busy_timeout_ms: int = Field(default=5000, alias="SQLITE_BUSY_TIMEOUT_MS", ge=100, le=60000)
    pending_action_expire_minutes: int = Field(default=30, alias="PENDING_ACTION_EXPIRE_MINUTES", ge=1, le=1440)
    processing_stale_minutes: int = Field(default=15, alias="PROCESSING_STALE_MINUTES", ge=1, le=1440)
    maintenance_interval_minutes: int = Field(default=60, alias="MAINTENANCE_INTERVAL_MINUTES", ge=1, le=1440)
    reminder_dedup_hours: int = Field(default=24, alias="REMINDER_DEDUP_HOURS", ge=1, le=720)
    month_end_reminder_days: int = Field(default=3, alias="MONTH_END_REMINDER_DAYS", ge=1, le=10)
    action_retention_days: int = Field(default=30, alias="ACTION_RETENTION_DAYS", ge=1, le=3650)
    reminder_retention_days: int = Field(default=90, alias="REMINDER_RETENTION_DAYS", ge=1, le=3650)

    cors_origins: str = Field(default="http://localhost:3000,http://127.0.0.1:3000", alias="CORS_ORIGINS")
    cors_allow_credentials: bool = Field(default=False, alias="CORS_ALLOW_CREDENTIALS")
    max_request_body_bytes: int = Field(default=1_048_576, alias="MAX_REQUEST_BODY_BYTES", ge=1024, le=10_485_760)
    rate_limit_requests: int = Field(default=60, alias="RATE_LIMIT_REQUESTS", ge=1, le=10000)
    rate_limit_window_seconds: int = Field(default=60, alias="RATE_LIMIT_WINDOW_SECONDS", ge=1, le=3600)

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_path: str = Field(default="logs/agent.log", alias="LOG_PATH")
    log_backup_count: int = Field(default=14, alias="LOG_BACKUP_COUNT", ge=1, le=365)

    @field_validator("default_digit_code", "default_restaurant_id", "default_meal_id", mode="before")
    @classmethod
    def empty_optional_integer_as_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"

    def resolve_path(self, value: str) -> Path:
        path = Path(value).expanduser()
        return path if path.is_absolute() else (BASE_DIR / path).resolve()

    @property
    def sqlite_file(self) -> Path:
        return self.resolve_path(self.sqlite_path)

    @property
    def log_file(self) -> Path:
        return self.resolve_path(self.log_path)

    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in (self.cors_origins or "").split(",") if item.strip()]

    def allowed_host_list(self) -> list[str]:
        return [item.strip() for item in (self.allowed_hosts or "").split(",") if item.strip()]

    def ssl_verify_value(self) -> bool | str:
        if self.internal_ca_bundle:
            return str(self.resolve_path(self.internal_ca_bundle))
        return self.verify_ssl

    def validate_runtime(self) -> None:
        problems: list[str] = []
        if self.is_production:
            if self.auth_required and len(self.agent_api_key.get_secret_value()) < 32:
                problems.append("AGENT_API_KEY must contain at least 32 characters when Gateway authentication is enabled")
            if self.enable_admin_endpoints and len(self.admin_api_key.get_secret_value()) < 32:
                problems.append("ADMIN_API_KEY must contain at least 32 characters when admin endpoints are enabled")
            if not self.verify_ssl and not self.internal_ca_bundle:
                problems.append("TLS verification cannot be disabled in production")
            if "*" in self.cors_origin_list():
                problems.append("Wildcard CORS origin is not allowed in production")
            if self.app_debug:
                problems.append("APP_DEBUG must be false in production")
            if self.forwarded_allow_ips.strip() == "*":
                problems.append("FORWARDED_ALLOW_IPS cannot be wildcard in production")
        if self.cors_allow_credentials and "*" in self.cors_origin_list():
            problems.append("Credentials cannot be combined with wildcard CORS")
        try:
            ZoneInfo(self.app_timezone)
        except ZoneInfoNotFoundError:
            problems.append("APP_TIMEZONE is not a valid IANA timezone")
        if problems:
            raise RuntimeError("; ".join(problems))

    def config_status(self) -> dict[str, Any]:
        return {
            "appName": self.app_name,
            "appVersion": self.app_version,
            "appEnv": self.app_env,
            "authenticationRequired": self.auth_required,
            "adminEndpointsEnabled": self.enable_admin_endpoints,
            "integrationMode": "existing-backend-contract" if not self.auth_required else "trusted-gateway",
            "tlsVerificationEnabled": bool(self.verify_ssl or self.internal_ca_bundle),
            "docsEnabled": self.enable_docs,
            "stateStorage": "sqlite-local",
            "runtimeMode": "real-api-only-no-fallback",
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
