from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    database_url: str = "sqlite:///./sample_sentinel.db"
    threshold: float = Field(default=0.95, validation_alias=AliasChoices("THRESHOLD", "threshold"))
    max_concurrency: int = 4
    batch_size: int = 100
    embedding_model: str = "all-MiniLM-L6-v2"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
