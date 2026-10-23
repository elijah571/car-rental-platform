from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit

from pydantic import Field, SecretStr
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


class Settings(BaseSettings):
    auth_service_api_key: SecretStr | None = Field(default=None, validation_alias="AUTH_SERVICE_API_KEY")
    jwt_secret: SecretStr = Field(validation_alias="JWT_SECRET")
    jwt_refresh_secret: SecretStr = Field(validation_alias="JWT_REFRESH_SECRET")
    jwt_access_expire: str = Field(default="50m", validation_alias="JWT_ACCESS_EXPIRE")
    jwt_refresh_expire: str = Field(default="7d", validation_alias="JWT_REFRESH_EXPIRE")
    redis_url: SecretStr | None = Field(default=None, validation_alias="REDIS_URL")
    redis_cloud_url: SecretStr | None = Field(default=None, validation_alias="REDIS_CLOUD_URL")
    smtp_host: str | None = Field(default=None, validation_alias="SMTP_HOST")
    smtp_port: int = Field(default=465, validation_alias="SMTP_PORT")
    email_user: str | None = Field(default=None, validation_alias="EMAIL_USER")
    email_password: SecretStr | None = Field(default=None, validation_alias="EMAIL_PASS")
    email_from: str | None = Field(default=None, validation_alias="EMAIL_FROM")
    platform_admin_emails: str = Field(default="", validation_alias="PLATFORM_ADMIN_EMAILS")
    environment: str = Field(default="development", validation_alias="NODE_ENV")
    allow_dev_verification_code: bool = Field(default=False, validation_alias="AUTH_ALLOW_DEV_VERIFICATION_CODE")
    database_url_override: str | None = Field(default=None, validation_alias="DATABASE_URL")
    postgres_user: str | None = Field(default=None, validation_alias="POSTGRES_USER")
    postgres_password: str | None = Field(default=None, validation_alias="POSTGRES_PASSWORD")
    postgres_db: str | None = Field(default=None, validation_alias="POSTGRES_DB")
    postgres_host: str = Field(default="127.0.0.1", validation_alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5433, validation_alias="POSTGRES_PORT")
    cors_allowed_origins: str = Field(default="http://localhost:5173,http://127.0.0.1:5173", validation_alias="CORS_ALLOWED_ORIGINS")

    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return _async_database_url(self.database_url_override)
        if not self.postgres_user or not self.postgres_password or not self.postgres_db:
            raise ValueError("Set DATABASE_URL or all POSTGRES_* credentials to use the database.")
        return (
            f"postgresql+asyncpg://{quote_plus(self.postgres_user)}:{quote_plus(self.postgres_password)}"
            f"@{self.postgres_host}:{self.postgres_port}/{quote_plus(self.postgres_db)}"
        )

    @property
    def database_configured(self) -> bool:
        return bool(self.database_url_override or (self.postgres_user and self.postgres_password and self.postgres_db))

    @property
    def redis_connection_url(self) -> str:
        configured = self.redis_url or self.redis_cloud_url
        return configured.get_secret_value() if configured else "redis://127.0.0.1:6380/0"

    @property
    def admin_email_set(self) -> frozenset[str]:
        return frozenset(email.strip().lower() for email in self.platform_admin_emails.split(",") if email.strip())

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.email_user and self.email_password)


@lru_cache
def get_settings() -> Settings:
    return Settings()
