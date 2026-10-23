"""Central configuration loaded from environment variables (never hard-code secrets)."""
from __future__ import annotations

import os

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET = "development-only-change-me"
PRODUCTION_FRONTEND = "https://bidsynq-frontend.onrender.com"


class Settings(BaseSettings):
    # Application security
    secret_key: str = DEFAULT_SECRET
    access_token_minutes: int = Field(default=60, ge=1, le=1440)

    # Database. SQLite is only a local-development convenience; the production
    # check below refuses to start on Render without PostgreSQL.
    database_url: str = "sqlite:///./bidsynq.db"

    # Registration and permissions
    bidsynq_allow_admin_registration: bool = False

    # Groq AI (optional). Calls are made with HTTPX; no SDK is used.
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_timeout_seconds: float = Field(default=35.0, ge=3, le=120)

    # Document uploads
    max_document_mb: int = Field(default=15, ge=1, le=50)
    max_documents_per_tender: int = Field(default=20, ge=1, le=200)
    document_storage_dir: str = "storage/tender_documents"

    # Comma-separated browser origins allowed to call the API
    cors_origins: str = f"{PRODUCTION_FRONTEND},http://localhost:3000,http://127.0.0.1:3000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # People often paste values with stray spaces/newlines into dashboards.
    @field_validator("secret_key", "database_url", "groq_api_key", "groq_model", "cors_origins", mode="before")
    @classmethod
    def _strip(cls, value):
        return value.strip() if isinstance(value, str) else value

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]
        if "*" in origins:
            raise ValueError("CORS_ORIGINS must list explicit origins; '*' is not allowed")
        return origins

    @property
    def is_production(self) -> bool:
        # Render sets RENDER=true on every service. BIDSYNQ_ENV=production is a manual override.
        return bool(os.getenv("RENDER")) or os.getenv("BIDSYNQ_ENV", "").lower() == "production"


settings = Settings()


def validate_production_settings(cfg: Settings = settings) -> None:
    """Fail fast with a clear message instead of running insecurely in production."""
    if not cfg.is_production:
        return
    problems: list[str] = []
    if cfg.secret_key == DEFAULT_SECRET or len(cfg.secret_key) < 32:
        problems.append(
            "SECRET_KEY must be set to a random value of at least 32 characters "
            "(generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\")"
        )
    if not cfg.database_url.startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
        problems.append("DATABASE_URL must point to PostgreSQL in production (SQLite is not allowed)")
    if cfg.bidsynq_allow_admin_registration:
        problems.append("BIDSYNQ_ALLOW_ADMIN_REGISTRATION must be false in production")
    try:
        cfg.cors_origin_list
    except ValueError as exc:
        problems.append(str(exc))
    if problems:
        raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))
