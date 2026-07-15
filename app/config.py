from pydantic import BaseModel, EmailStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./saas.db"
    port: int = 8000
    cors_origins: str = "*"
    internal_api_secret: str = ""
    multi_device_test_emails: str = "test@greciaplanner.ro"


settings = Settings()


class GrantProRequest(BaseModel):
    email: EmailStr
    island_id: str | None = None
    source_order_id: str | None = None
