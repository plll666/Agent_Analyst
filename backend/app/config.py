from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки backend, читаются из окружения."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+asyncpg://agent_analyst:agent_analyst@localhost:5432/agent_analyst"
    )
    secret_key: str = "dev-secret-key-change-me-32-bytes"
    access_token_ttl_minutes: int = 60
    cookie_secure: bool = False


@lru_cache
def get_settings() -> Settings:
    """Настройки один раз на процесс — движок создаётся один раз."""
    return Settings()
