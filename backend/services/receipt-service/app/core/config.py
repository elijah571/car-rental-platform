from functools import lru_cache
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from urllib.parse import quote_plus


class Settings(BaseSettings):
    receipt_service_api_key: SecretStr | None = Field(
        default=None, validation_alias="RECEIPT_SERVICE_API_KEY"
    )
    database_url_override: str | None = Field(default=None, validation_alias="DATABASE_URL")
    postgres_user: str | None = Field(default=None, validation_alias="POSTGRES_USER")
    postgres_password: str | None = Field(default=None, validation_alias="POSTGRES_PASSWORD")
    postgres_db: str | None = Field(default=None, validation_alias="POSTGRES_DB")
    postgres_host: str = Field(default="127.0.0.1", validation_alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5433, validation_alias="POSTGRES_PORT")

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
            return self.database_url_override
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
