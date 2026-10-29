"""Application settings, read from the environment and `.env` (see `.env.example`)."""

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from cryptography.fernet import Fernet, InvalidToken
from pydantic import field_validator, model_validator
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

# Secrets saved from the web Settings page are Fernet-encrypted with FERNET_KEY.
SECRET_FIELDS = ("llm_api_key", "smtp_app_password")
ENC_PREFIX = "fernet:"


def encrypt_secret(value: str, key: str) -> str:
    return ENC_PREFIX + Fernet(key.encode()).encrypt(value.encode()).decode()


def decrypt_secret(value: str, key: str) -> str:
    """ "" when it can't be decrypted (no key, or another key): the user enters it again."""
    try:
        return Fernet(key.encode()).decrypt(value.removeprefix(ENC_PREFIX).encode()).decode()
    except (InvalidToken, ValueError):
        return ""


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
    # v0.1 ships English-only. Letters in other languages (templates, RTL) stay in the code;
    # add them here to re-enable, e.g. ENABLED_LETTER_LANGUAGES='["en","ur"]'.
    enabled_letter_languages: list[str] = ["en"]
    web_origin: str = "http://localhost:3000"  # the only origin CORS allows (the web app)
    # The retired Streamlit UI's origin (`make dev-ui-legacy`). Empty: the API trusts only the
    # web app. Any origin listed here is trusted for whatever runs on that local port.
    ui_origin: str = ""
    # Host headers the API answers (DNS-rebinding protection). Hosted mode: add your domain.
    allowed_hosts: str = "localhost,127.0.0.1"
    allow_lan: bool = False  # Docker publishes ports on the LAN only when true: NO login!
    # Private/loopback addresses LLM_BASE_URL or SMTP_HOST may use (a local model or relay).
    # Link-local and cloud-metadata addresses are always refused (escalate/netguard.py).
    local_endpoint_hosts: str = "localhost,127.0.0.1,::1,ollama,host.docker.internal"
    allow_demo_seed: bool = True
    # Optional app lock (escalate/api/applock.py): a passcode, plain or an argon2 hash. Unset =
    # no lock. Not user accounts: v0.1 is single-user (SECURITY.md, "Why there's no login").
    app_passcode: str = ""
    api_docs: bool = False  # /docs and /redoc (CDN scripts): development only
    app_session_hours: int = 12
    demo_mode: bool = False

    # Not in .env.example; sensible defaults that rarely need changing.
    checkpoint_db: Path = Path("./data/checkpoints.db")
    playbooks_dir: Path = Path("./playbooks")
    templates_dir: Path = Path("./templates")
    max_upload_mb: int = 25

    # Safety limits (task 4.2).
    max_new_cases_per_hour: int = 10
    # Per client, per minute (escalate/api/limits.py). AI calls are slow and may cost money.
    rate_limit_writes_per_minute: int = 120
    rate_limit_ai_per_minute: int = 20
    max_json_body_kb: int = 1024  # uploads are capped separately by max_upload_mb
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

    @model_validator(mode="after")
    def _decrypt_saved_secrets(self) -> "Settings":
        for name in SECRET_FIELDS:
            value = getattr(self, name)
            if isinstance(value, str) and value.startswith(ENC_PREFIX):
                setattr(self, name, decrypt_secret(value, self.fernet_key))
        return self

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


def env_file_problems(path: Path = Path(".env")) -> list[str]:
    """Keys set more than once in `.env`: the last line wins, often an empty template line that
    hides the real value (e.g. a second, blank FERNET_KEY=). Values are never included."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    seen: dict[str, list[int]] = {}
    for n, line in enumerate(lines, 1):
        key, sep, _ = line.strip().partition("=")
        if sep and key and not key.startswith("#"):
            seen.setdefault(key.strip().upper(), []).append(n)
    return [
        f"{key} is set {len(at)} times in {path} (lines {', '.join(map(str, at))}); "
        "the last one wins, so remove the others"
        for key, at in seen.items()
        if len(at) > 1
    ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
