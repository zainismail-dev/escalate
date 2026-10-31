from pathlib import Path

import pytest

from escalate.config import Settings


def test_settings_read_every_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    env = {
        "LLM_BASE_URL": "http://x/v1",
        "LLM_API_KEY": "k",
        "MODEL_SMART": "m1",
        "MODEL_FAST": "m2",
        "CLOUD_PRIVACY_WARNING": "false",
        "DATABASE_URL": "sqlite://",
        "EVIDENCE_DIR": "/tmp/ev",
        "FERNET_KEY": "f",
        "OCR_LANGS": "eng+urd",
        "EMAIL_MODE": "gmail_api",
        "SMTP_USER": "u",
        "SMTP_APP_PASSWORD": "p",
        "DEFAULT_COUNTRY": "pk",
        "DEMO_MODE": "true",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    s = Settings(_env_file=None)
    assert s.llm_base_url == "http://x/v1"
    assert (s.model_smart, s.model_fast) == ("m1", "m2")
    assert s.cloud_privacy_warning is False
    assert s.ocr_langs == "eng+urd"
    assert s.email_mode == "gmail_api"
    assert s.default_country == "PK"
    assert s.demo_mode is True


def test_blank_default_country_means_ask(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEFAULT_COUNTRY", "")
    assert Settings(_env_file=None).default_country is None


def test_tests_never_use_the_real_data_folder() -> None:
    """conftest points every path the app writes or deletes away from ./data (delete-all once
    removed the developer's real evidence folders)."""
    from escalate.config import get_settings

    get_settings.cache_clear()
    s = get_settings()
    real = (Path(__file__).parents[1] / "data").resolve()
    for path in (s.evidence_dir, s.checkpoint_db):
        assert not Path(path).resolve().is_relative_to(real), path
    get_settings.cache_clear()
