"""Application settings, read from the environment and `.env` (see `.env.example`)."""

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import field_validator
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

# Values saved from the web Settings page. They win over the environment and `.env`, so the
# page works the same in Docker (where compose sets env vars) and locally.
SETTINGS_FILE_ENV = "ESCALATE_SETTINGS_FILE"


def settings_file() -> Path:
    return Path(os.environ.get(SETTINGS_FILE_ENV, "./data/settings.json"))


class _SavedSettings(PydanticBaseSettingsSource):
    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        return None, field_name, False  # unused: __call__ returns everything at once

    def __call__(self) -> dict[str, Any]:
        path = settings_file()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}


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
    smtp_host: str = "smtp.gmail.com"  # any provider: port 465 = SSL, other ports = STARTTLS
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_app_password: str = ""

    default_country: str | None = None
    default_language: str = "en"  # BCP-47 letter language for new cases
    web_origin: str = "http://localhost:3000"  # the only origin CORS allows (the web app)
    allow_demo_seed: bool = True
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

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Tests pass explicit values (init) and must not see a developer's saved settings.
        saved = _SavedSettings(settings_cls)
        return init_settings, saved, env_settings, dotenv_settings, file_secret_settings

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
