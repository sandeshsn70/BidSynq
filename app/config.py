
import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration loaded from environment variables."""

    # Application security
    secret_key: str = "development-only-change-me"
    access_token_minutes: int = 60

    # Database
    database_url: str = "sqlite:///./bidsynq.db"

    # Registration and permissions
    bidsynq_allow_admin_registration: bool = False

    # Groq AI
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # Document upload limit
    max_document_mb: int = 15

    # Comma-separated frontend origins
    cors_origins: str = (
        "http://localhost:3000,"
        "http://127.0.0.1:3000"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


settings = Settings()
