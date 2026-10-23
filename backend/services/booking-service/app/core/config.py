from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit

from pydantic import Field, field_validator
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


_ENV_FILE = next(
    (parent / ".env" for parent in Path(__file__).resolve().parents if (parent / ".env.example").is_file()),
    Path(".env"),
)


def _async_database_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"postgres", "postgresql", "postgresql+asyncpg"}:
        return url
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    sslmode = query.pop("sslmode", None)
    query.pop("channel_binding", None)
    if sslmode:
        query["ssl"] = sslmode
    return urlunsplit(("postgresql+asyncpg", parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def _http_url(value: str | None) -> str | None:
    if value and not value.startswith(("http://", "https://")):
        return f"http://{value}"
    return value


class Settings(BaseSettings):
    jwt_secret: SecretStr = Field(validation_alias="JWT_SECRET")
    car_service_url: str = Field(default="http://127.0.0.1:8002", validation_alias="CAR_SERVICE_URL")
    booking_hold_minutes: int = Field(default=15, validation_alias="BOOKING_HOLD_MINUTES", ge=1, le=15)
    payment_to_booking_api_key: SecretStr | None = Field(
        default=None, validation_alias="PAYMENT_TO_BOOKING_API_KEY"
    )
    payment_service_api_key: SecretStr | None = Field(
        default=None, validation_alias="PAYMENT_SERVICE_API_KEY"
    )
    payment_service_url: str = Field(default="http://127.0.0.1:8004", validation_alias="PAYMENT_SERVICE_URL")
    receipt_service_url: str = Field(default="http://127.0.0.1:8005", validation_alias="RECEIPT_SERVICE_URL")
    receipt_service_api_key: SecretStr | None = Field(default=None, validation_alias="RECEIPT_SERVICE_API_KEY")
    auth_service_url: str = Field(default="http://127.0.0.1:8000", validation_alias="AUTH_SERVICE_URL")
    auth_service_api_key: SecretStr | None = Field(default=None, validation_alias="AUTH_SERVICE_API_KEY")
    rental_agreement_version: str = Field(default="draft-1", validation_alias="RENTAL_AGREEMENT_VERSION")
    notification_service_url: str = Field(default="http://127.0.0.1:8003", validation_alias="NOTIFICATION_SERVICE_URL")
    notification_service_api_key: SecretStr | None = Field(
        default=None, validation_alias="NOTIFICATION_SERVICE_API_KEY"
    )
    platform_admin_emails: str = Field(default="", validation_alias="PLATFORM_ADMIN_EMAILS")
    return_reminder_minutes: int = Field(default=60, validation_alias="RETURN_REMINDER_MINUTES", ge=5, le=240)
    database_url_override: str | None = Field(default=None, validation_alias="DATABASE_URL")
    postgres_user: str | None = Field(default=None, validation_alias="POSTGRES_USER")
    postgres_password: str | None = Field(default=None, validation_alias="POSTGRES_PASSWORD")
    postgres_db: str | None = Field(default=None, validation_alias="POSTGRES_DB")
    postgres_host: str = Field(default="127.0.0.1", validation_alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5433, validation_alias="POSTGRES_PORT")
    cors_allowed_origins: str = Field(default="http://localhost:5173,http://127.0.0.1:5173", validation_alias="CORS_ALLOWED_ORIGINS")

    @field_validator('car_service_url', 'payment_service_url', 'receipt_service_url', 'auth_service_url', 'notification_service_url', mode="before")
    @classmethod
    def normalize_service_urls(cls, value: str | None) -> str | None:
        return _http_url(value)

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def database_configured(self) -> bool:
        return bool(
            self.database_url_override
            or (self.postgres_user and self.postgres_password and self.postgres_db)
        )

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return _async_database_url(self.database_url_override)
        if not self.database_configured:
            raise ValueError("Set DATABASE_URL or all POSTGRES_* credentials to use the database.")
        username = quote_plus(self.postgres_user or "")
        password = quote_plus(self.postgres_password or "")
        database = quote_plus(self.postgres_db or "")
        return (
            f"postgresql+asyncpg://{username}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{database}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
