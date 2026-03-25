from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Конфигурация приложения, загружается из переменных окружения."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str
    db_path: str = "sqlite:///./math_bot.db"
    admin_ids: List[int] = []
    free_daily_limit: int = 3
    subscription_price_rub: int = 199
    subscription_duration_days: int = 30
    enable_tesseract_ocr: bool = False
    log_level: str = "INFO"

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return []
            return [int(part.strip()) for part in value.split(",") if part.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
