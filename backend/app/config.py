from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "BrandProof AI"
    database_url: str = "sqlite:///./brandproof.db"
    demo_mode: bool = True
    llm_provider: str = "rules-only"
    llm_api_key: str | None = None
    llm_model: str = "gemini-2.0-flash"
    max_upload_bytes: int = 10 * 1024 * 1024
    storage_dir: str = "uploads"
    cors_origins: str = "http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
