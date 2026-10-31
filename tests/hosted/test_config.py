"""DEPLOY_MODE=hosted: refuse to start on a missing or unsafe setting; ignore saved settings."""

import json
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from escalate.config import HostedConfigError, Settings, get_settings, hosted_problems
from tests.hosted.conftest import HOSTED_ENV


def hosted(**overrides: object) -> Settings:
    values: dict[str, object] = {k.lower(): v for k, v in HOSTED_ENV.items()}
    values.update(
        database_url="postgresql://u:p@pooler.example.com:5432/postgres",
        fernet_key=Fernet.generate_key().decode(),
    )
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def test_local_mode_is_the_default_and_needs_nothing() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.deploy_mode == "local" and not s.hosted
    assert hosted_problems(s) == []


def test_complete_hosted_settings_pass() -> None:
    assert hosted_problems(hosted()) == []


@pytest.mark.parametrize(
    ("field", "value", "needle"),
    [
        ("database_url", "sqlite:///./escalate.db", "DATABASE_URL"),
        ("fernet_key", "", "FERNET_KEY"),
        ("fernet_key", "not-a-key", "FERNET_KEY"),
        ("supabase_url", "", "SUPABASE_URL"),
        ("supabase_url", "http://testproject.supabase.co", "SUPABASE_URL"),
        ("supabase_service_role_key", "", "SUPABASE_SERVICE_ROLE_KEY"),
        ("llm_base_url", "http://localhost:11434/v1", "LLM_BASE_URL"),
        ("llm_api_key", "ollama", "LLM_API_KEY"),
        ("llm_api_key", "", "LLM_API_KEY"),
        ("model_smart", "", "MODEL_SMART"),
        ("web_origin", "http://localhost:3000", "WEB_ORIGIN"),
        ("web_origin", "https://localhost:3000", "WEB_ORIGIN"),
        ("allowed_hosts", "localhost,127.0.0.1", "ALLOWED_HOSTS"),
        ("tick_secret", "", "TICK_SECRET"),
        ("tick_secret", "short", "TICK_SECRET"),
        ("demo_mode", True, "DEMO_MODE"),
    ],
)
def test_each_missing_or_unsafe_value_refuses_to_start(
    field: str, value: object, needle: str
) -> None:
    problems = hosted_problems(hosted(**{field: value}))
    assert len(problems) == 1 and needle in problems[0], problems


def test_problems_never_include_values() -> None:
    s = hosted(llm_api_key="", supabase_service_role_key="", fernet_key="sekrit-value")
    text = str(HostedConfigError(hosted_problems(s)))
    assert "sekrit-value" not in text and "test-groq-key" not in text


def test_create_app_refuses_to_start_in_hosted_mode_with_sqlite(
    hosted_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from escalate.api.main import create_app

    monkeypatch.setenv("DATABASE_URL", "sqlite:///./escalate.db")
    get_settings.cache_clear()
    with pytest.raises(HostedConfigError, match="DATABASE_URL"):
        create_app(startup=False)


def test_db_schema_must_be_a_plain_name() -> None:
    with pytest.raises(ValueError, match="DB_SCHEMA"):
        hosted(db_schema='escalate"; drop table x; --')


def test_hosted_mode_ignores_the_saved_settings_file(
    hosted_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Users can't change the AI provider in hosted mode, even through a stray settings file."""
    saved = tmp_path / "settings.json"
    saved.write_text(json.dumps({"llm_base_url": "http://169.254.169.254/", "model_smart": "x"}))
    monkeypatch.setenv("ESCALATE_SETTINGS_FILE", str(saved))
    get_settings.cache_clear()
    s = get_settings()
    assert s.llm_base_url == HOSTED_ENV["LLM_BASE_URL"] and s.model_smart == "fake-smart"
