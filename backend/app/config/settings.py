from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = Field(default="InterSignal API", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_version: str = Field(default="0.1.0", alias="APP_VERSION")
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    supabase_url: str | None = Field(default=None, alias="SUPABASE_URL")
    supabase_anon_key: str | None = Field(default=None, alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: str | None = Field(
        default=None,
        alias="SUPABASE_SERVICE_ROLE_KEY",
    )
    frontend_url: str = Field(default="http://localhost:5173", alias="FRONTEND_URL")
    log_level: str | None = Field(default=None, alias="LOG_LEVEL")
    groww_totp_token: str | None = Field(default=None, alias="GROWW_TOTP_TOKEN")
    groww_totp_secret: str | None = Field(default=None, alias="GROWW_TOTP_SECRET")

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @property
    def effective_log_level(self) -> str:
        if self.log_level:
            return self.log_level.upper()
        if self.app_env.lower() in {"production", "prod"}:
            return "INFO"
        return "DEBUG"

    @property
    def supabase_configured(self) -> bool:
        has_url = bool(self.supabase_url)
        has_key = bool(self.supabase_service_role_key or self.supabase_anon_key)
        return has_url and has_key

    @property
    def groww_configured(self) -> bool:
        return bool(self.groww_totp_token and self.groww_totp_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()
