from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    jwt_secret: str
    access_token_expire_minutes: int = 60
    upload_dir: str = ""
    max_upload_bytes: int = 10_485_760
    max_document_characters: int = 350_000
    groq_api_key: str = ""
    groq_model: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:5174,http://localhost:5174"

    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def resolved_upload_dir(self) -> Path:
        if not self.upload_dir:
            return PROJECT_ROOT / "uploads"
        path = Path(self.upload_dir)
        if not path.is_absolute():
            return PROJECT_ROOT / path
        return path


settings = Settings()
