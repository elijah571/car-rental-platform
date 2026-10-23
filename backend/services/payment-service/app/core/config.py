from functools import lru_cache
from pydantic import SecretStr
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    stripe_secret_key: str | None = Field(default=None, validation_alias="STRIPE_SECRET_KEY")
    stripe_webhook_secret: str | None = Field(default=None, validation_alias="STRIPE_WEBHOOK_SECRET")
    stripe_publishable_key: str | None = Field(default=None, validation_alias="STRIPE_PUBLISHABLE_KEY")
    payment_service_api_key: SecretStr | None = Field(
        default=None, validation_alias="PAYMENT_SERVICE_API_KEY"
    )
    payment_to_booking_api_key: SecretStr | None = Field(
        default=None, validation_alias="PAYMENT_TO_BOOKING_API_KEY"
    )
    booking_service_url: str | None = Field(default=None, validation_alias="BOOKING_SERVICE_URL")
    receipt_service_url: str | None = Field(default=None, validation_alias="RECEIPT_SERVICE_URL")
    receipt_service_api_key: SecretStr | None = Field(
        default=None, validation_alias="RECEIPT_SERVICE_API_KEY"
    )
    auth_service_url: str | None = Field(default=None, validation_alias="AUTH_SERVICE_URL")
    auth_service_api_key: SecretStr | None = Field(default=None, validation_alias="AUTH_SERVICE_API_KEY")
    notification_service_url: str | None = Field(default=None, validation_alias="NOTIFICATION_SERVICE_URL")
    notification_service_api_key: SecretStr | None = Field(
        default=None, validation_alias="NOTIFICATION_SERVICE_API_KEY"
    )
    database_url_override: str | None = Field(default=None, validation_alias="DATABASE_URL")
    postgres_user: str | None = Field(default=None, validation_alias="POSTGRES_USER")
    postgres_password: str | None = Field(default=None, validation_alias="POSTGRES_PASSWORD")
    postgres_db: str | None = Field(default=None, validation_alias="POSTGRES_DB")
    postgres_host: str = Field(default="127.0.0.1", validation_alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5433, validation_alias="POSTGRES_PORT")

    @field_validator('booking_service_url', 'receipt_service_url', 'auth_service_url', 'notification_service_url', mode="before")
    @classmethod
    def normalize_service_urls(cls, value: str | None) -> str | None:
        return _http_url(value)

    model_config = SettingsConfigDict(
        env_file="../../../.env",
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
