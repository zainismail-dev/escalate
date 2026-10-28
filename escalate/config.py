"""Application settings, read from the environment and `.env` (see `.env.example`)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # LLM: any OpenAI-compatible endpoint. Default is local Ollama.
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    model_smart: str = ""
    model_fast: str = ""
    cloud_privacy_warning: bool = True

    database_url: str = "sqlite:///./escalate.db"
    evidence_dir: Path = Path("./data/evidence")
    fernet_key: str = ""
    ocr_langs: str = "eng"

    email_mode: Literal["smtp", "gmail_api"] = "smtp"
    smtp_user: str = ""
    smtp_app_password: str = ""

    default_country: str | None = None
    demo_mode: bool = False

    # Not in .env.example; sensible defaults that rarely need changing.
    checkpoint_db: Path = Path("./data/checkpoints.db")
    playbooks_dir: Path = Path("./playbooks")
    templates_dir: Path = Path("./templates")
    max_upload_mb: int = 25

    # Safety limits (task 4.2).
    max_new_cases_per_hour: int = 10
    require_evidence: bool = True
    max_cases_per_recipient: int = 3  # within recipient_window_days: a harassment pattern
    recipient_window_days: int = 30
    demo_upload_mb: int = 5
    demo_retention_hours: int = 24

    @property
    def upload_limit_mb(self) -> int:
        return (
            min(self.max_upload_mb, self.demo_upload_mb) if self.demo_mode else self.max_upload_mb
        )

    @field_validator("default_country", mode="before")
    @classmethod
    def _blank_country_is_none(cls, v: object) -> object:
        if isinstance(v, str):
            v = v.strip().upper()
            return v or None
        return v

    @property
    def model_fast_or_smart(self) -> str:
        return self.model_fast or self.model_smart


@lru_cache
def get_settings() -> Settings:
    return Settings()
