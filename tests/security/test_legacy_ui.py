"""Second review N1/N3: the Streamlit dev UI answered any Host (DNS rebinding) and logged in
with a stored passcode through a shared cookie jar. It is retired: not in compose or the
default make targets, opt-in only, locked to localhost, no auto-login."""

import ast
import tomllib
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from escalate.api.main import create_app
from escalate.config import get_settings
from tests.factories import APP_BASE_URL

REPO = Path(__file__).resolve().parents[2]


def test_compose_has_no_streamlit_service() -> None:
    compose = yaml.safe_load((REPO / "docker-compose.yml").read_text())
    for name, svc in compose["services"].items():
        assert "streamlit" not in str(svc.get("command", "")).lower(), name
        assert not any("8501" in str(p) for p in svc.get("ports", [])), name
    assert "ui" not in compose["services"]


def _target(make: str, name: str) -> str:
    start = make.index(f"\n{name}:")
    nxt = make.find("\n\n", start + 1)
    return make[start : nxt if nxt != -1 else None]


def test_default_make_targets_do_not_run_streamlit() -> None:
    make = (REPO / "Makefile").read_text()
    for target in ("up", "setup", "api", "web-dev", "logs"):
        assert "streamlit" not in _target(make, target).lower(), target
    legacy = _target(make, "dev-ui-legacy")
    assert "UNSUPPORTED" in legacy and "streamlit run ui/app.py" in legacy


def test_legacy_ui_is_locked_to_localhost_with_xsrf() -> None:
    cfg = tomllib.loads((REPO / ".streamlit" / "config.toml").read_text())["server"]
    assert cfg["address"] == "127.0.0.1"
    assert cfg["allowedHosts"] == ["localhost", "127.0.0.1"]
    assert cfg["enableXsrfProtection"] is True


def test_legacy_ui_client_has_no_auto_login_or_shared_cookies() -> None:
    raw = (REPO / "ui" / "api_client.py").read_text()
    src = "\n".join(line.split("#", 1)[0] for line in raw.splitlines())  # code, not comments
    tree = ast.parse(raw)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "UI_PASSCODE" not in src and "APP_PASSCODE" not in src
    assert "/auth/login" not in src
    assert "Cookies" not in names and "cookies" not in src


def test_api_no_longer_trusts_the_streamlit_origin_by_default(
    monkeypatch: pytest.MonkeyPatch, db: Session
) -> None:
    monkeypatch.delenv("UI_ORIGIN", raising=False)
    get_settings.cache_clear()
    headers = {"Origin": "http://localhost:8501", "X-Escalate-Request": "1"}
    with TestClient(create_app(startup=False), base_url=APP_BASE_URL, headers=headers) as c:
        assert c.post("/privacy/delete-all", json={"confirm": True}).status_code == 403
    monkeypatch.setenv("UI_ORIGIN", "http://localhost:8501")  # opt-in for the legacy UI
    get_settings.cache_clear()
    with TestClient(create_app(startup=False), base_url=APP_BASE_URL, headers=headers) as c:
        assert c.post("/privacy/delete-all", json={"confirm": True}).status_code == 204
    get_settings.cache_clear()
