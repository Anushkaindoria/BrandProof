from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "BrandProof AI"
    database_url: str = "sqlite:///./brandproof.db"
    demo_mode: bool = True
    llm_provider: str = "rules-only"
    llm_api_key: str | None = None
    max_upload_bytes: int = 10 * 1024 * 1024
    cors_origins: str = "http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
