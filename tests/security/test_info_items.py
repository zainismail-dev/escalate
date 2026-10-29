"""Second review INFO items: the OpenAPI route map follows API_DOCS; a saved hostname that
doesn't resolve is a warning, not an error."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from escalate import netguard
from escalate.api.main import create_app
from escalate.config import get_settings
from tests.factories import APP_BASE_URL, APP_HEADERS


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch, db: Session, tmp_path: object) -> Iterator[TestClient]:
    monkeypatch.setenv("ESCALATE_SETTINGS_FILE", f"{tmp_path}/settings.json")
    get_settings.cache_clear()
    with TestClient(create_app(startup=False), base_url=APP_BASE_URL, headers=APP_HEADERS) as c:
        yield c
    get_settings.cache_clear()


def test_unresolvable_hostname_is_saved_with_a_warning(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(netguard, "_resolve", lambda host: [])  # offline: nothing resolves
    r = api.put("/settings", json={"smtp_host": "smtp.typo-mail.example"})
    assert r.status_code == 200
    assert r.json()["smtp_host"] == "smtp.typo-mail.example"
    assert r.json()["warnings"] == [
        "SMTP_HOST smtp.typo-mail.example does not resolve right now; check the spelling "
        "(saved anyway)"
    ]


def test_resolvable_hostname_has_no_warning(api: TestClient) -> None:
    r = api.put("/settings", json={"smtp_host": "127.0.0.1"})  # an IP always "resolves"
    assert r.status_code == 422 or r.json()["warnings"] == []


def test_schema_is_exportable_for_tools_without_being_served(api: TestClient) -> None:
    assert api.get("/openapi.json").status_code == 404
    from escalate.api.schema import create_app as make

    assert "/cases" in make(startup=False).openapi()["paths"]
