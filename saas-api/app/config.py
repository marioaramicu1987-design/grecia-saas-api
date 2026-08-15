from pydantic import BaseModel, EmailStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(url: str) -> str:
    """SQLAlchemy 2 nu acceptă schema heroku `postgres://`."""
    value = (url or "").strip()
    if not value:
        return "sqlite:///./saas.db"
    if value.startswith("postgres://"):
        return "postgresql://" + value[len("postgres://") :]
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./saas.db"
    port: int = 8000
    cors_origins: str = "*"
    internal_api_secret: str = ""
    multi_device_test_emails: str = "test@greciaplanner.ro"

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_db_url(cls, value: object) -> str:
        return normalize_database_url(str(value or ""))


settings = Settings()


class GrantProRequest(BaseModel):
    email: EmailStr
    island_id: str | None = None
    source_order_id: str | None = None


class CreateUnlockCodeRequest(BaseModel):
    island_id: str
    code: str | None = None
    note: str | None = None
    created_by: str | None = None


class RevokeUnlockCodeRequest(BaseModel):
    code: str
