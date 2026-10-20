from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


_ENV_FILE = next(
    (parent / ".env" for parent in Path(__file__).resolve().parents if (parent / ".env.example").is_file()),
    Path(".env"),
)


def _async_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgresql://")
    return url


class Settings(BaseSettings):
    jwt_secret: SecretStr = Field(validation_alias="JWT_SECRET")
    database_url_override: str | None = Field(default=None, validation_alias="DATABASE_URL")
    postgres_user: str | None = Field(default=None, validation_alias="POSTGRES_USER")
    postgres_password: str | None = Field(default=None, validation_alias="POSTGRES_PASSWORD")
    postgres_db: str | None = Field(default=None, validation_alias="POSTGRES_DB")
    postgres_host: str = Field(default="127.0.0.1", validation_alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5433, validation_alias="POSTGRES_PORT")
    cors_allowed_origins: str = Field(default="http://localhost:5173,http://127.0.0.1:5173", validation_alias="CORS_ALLOWED_ORIGINS")

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
