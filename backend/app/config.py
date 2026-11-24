from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки backend, читаются из окружения."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+asyncpg://agent_analyst:agent_analyst@localhost:5432/agent_analyst"
    )
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "dev-secret-key-change-me-32-bytes"
    access_token_ttl_minutes: int = 60
    cookie_secure: bool = False

    # Лимиты импорта требований (контракт спринта 3, раздел 2.1): фронт читает
    # их из GET .../requirement-imports/capabilities, поэтому значения здесь —
    # единственный источник истины.
    import_max_file_bytes: int = 10 * 1024 * 1024  # 10 MiB
    import_max_text_chars: int = 200_000
    import_txt_encoding: str = "utf-8"
    # Распакованный объём DOCX и число записей архива: защита от «zip-бомбы»
    # и от разбора, который упирается не в лимит текста, а в лимит разбора.
    import_max_unpacked_bytes: int = 64 * 1024 * 1024
    import_max_archive_entries: int = 10_000
    import_storage_dir: str = "data/requirement-imports"
    llm_max_input_chars: int = 200_000


@lru_cache
def get_settings() -> Settings:
    """Настройки один раз на процесс."""
    return Settings()
