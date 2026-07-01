from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./xeno_crm.db"
    ANALYTICS_DB_PATH: str = "data/processed/messaging_analytics.duckdb"
    RAW_DATA_DIR: str = "data/raw"
    PROCESSED_DATA_DIR: str = "data/processed"
    SAMPLE_DATA_DIR: str = "data/sample"
    DOCS_DIR: str = "docs"
    SYNTHETIC_RANDOM_SEED: int = 42
    DEFAULT_SYNTHETIC_ROWS: int = 100000
    GROQ_API_KEY: str = ""
    LLM_PROVIDER: str = "groq"
    LLM_MODEL: str = "llama-3.3-70b-versatile"
    CHANNEL_SERVICE_URL: str = "http://localhost:8001"
    APP_ENV: str = "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()


def project_root() -> Path:
    return Path(__file__).resolve().parent


def resolve_path(relative_path: str) -> Path:
    return (project_root() / relative_path).resolve()
