from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5433/shop"
    checkpoint_url: str = "postgresql://postgres:postgres@localhost:5433/shop"
    redis_url: str = "redis://localhost:6380/0"
    catalog_source_url: str = "https://dummyjson.com"
    sync_mode: str = "inprocess"
    sync_interval_minutes: int = 60
    fake_llm: bool = True
    embed_mode: str = "hash"
    auto_sync: bool = False
    spa_dist: Path = Path("web/dist")
    page_size: int = 100


def get_settings() -> Settings:
    return Settings()
