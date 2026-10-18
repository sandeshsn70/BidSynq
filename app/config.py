from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    secret_key: str = "development-only-change-me"
    access_token_minutes: int = 60
    database_url: str = "sqlite:///./bidsynq.db"
    bidsynq_allow_admin_registration: bool = False
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    max_document_mb: int = 15
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
