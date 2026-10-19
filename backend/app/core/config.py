"""All configuration comes from environment variables (and the repo-root .env for local dev)."""

from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# config.py -> core -> app -> backend -> repo root. Path() handles spaces in folder names.
ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    # Real environment variables win over .env. A missing .env file is fine (CI, production).
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    env: str = "development"
    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = ""
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    frontend_origin: str = "http://localhost:5173"
    run_embedded_worker: bool = True

    groq_api_key: str = ""
    groq_model: str = ""
    telegram_bot_token: str = ""

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    @model_validator(mode="after")
    def check_jwt_secret(self) -> "Settings":
        # Fail at startup, not at the first login, if the signing secret is weak or missing.
        if self.env != "test" and len(self.jwt_secret) < 32:
            raise ValueError(
                "JWT_SECRET must be at least 32 characters. Generate one with: "
                'python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        return self


settings = Settings()
