"""Route inventory: every route is listed here on purpose. A new route fails this test until it
is added below, which is the moment to decide whether it changes state (CSRF guard, rate limit)
and whether it may be reached while the app is locked."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from escalate.api.applock import OPEN_ROUTES
from escalate.api.main import create_app
from escalate.api.security import STATE_CHANGING
from escalate.config import get_settings
from tests.factories import APP_BASE_URL, APP_HEADERS

ROUTES = {
    ("GET", "/health"),
    ("GET", "/auth/status"),
    ("POST", "/auth/login"),
    ("POST", "/auth/logout"),
    ("GET", "/checklist"),
    ("GET", "/countries"),
    ("GET", "/settings"),
    ("PUT", "/settings"),
    ("POST", "/settings/llm-test"),
    ("POST", "/privacy/delete-all"),
    ("POST", "/demo/seed"),
    ("POST", "/cases"),
    ("GET", "/cases"),
    ("GET", "/cases/{case_id}"),
    ("PATCH", "/cases/{case_id}"),
    ("DELETE", "/cases/{case_id}"),
    ("POST", "/cases/{case_id}/evidence"),
    ("POST", "/cases/{case_id}/start"),
    ("POST", "/cases/{case_id}/answers"),
    ("POST", "/cases/{case_id}/checklist/ack"),
    ("POST", "/cases/{case_id}/retry"),
    ("GET", "/cases/{case_id}/timeline"),
    ("POST", "/cases/{case_id}/replies"),
    ("POST", "/cases/{case_id}/resolution"),
    ("POST", "/cases/{case_id}/verdict"),
    ("GET", "/cases/{case_id}/export.pdf"),
    ("POST", "/cases/{case_id}/letter-language"),
    ("POST", "/cases/{case_id}/withdraw"),
    ("PUT", "/messages/{message_id}"),
    ("POST", "/messages/{message_id}/approve"),
    ("POST", "/messages/{message_id}/recipient"),
    ("POST", "/messages/{message_id}/reject"),
    ("POST", "/messages/{message_id}/confirm-delivery"),
    ("GET", "/messages/{message_id}/printable.pdf"),
    ("GET", "/messages/{message_id}/review"),
    ("GET", "/messages/{message_id}/preview"),
}
DOCS = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
FAKE_ID = "00000000-0000-4000-8000-000000000000"


def app_routes() -> set[tuple[str, str]]:
    """From the OpenAPI schema (included routers are nested in app.routes)."""
    paths = create_app(startup=False).openapi()["paths"]
    return {(method.upper(), path) for path, ops in paths.items() for method in ops}


def test_no_route_is_hidden_from_the_schema() -> None:
    """The inventory relies on the schema: a route with include_in_schema=False would escape."""
    import escalate.api.routes as pkg

    src = "".join(f.read_text() for f in Path(pkg.__file__).parent.glob("*.py"))
    assert "include_in_schema" not in src


def concrete(path: str) -> str:
    return path.replace("{case_id}", FAKE_ID).replace("{message_id}", FAKE_ID)


def test_route_inventory_is_complete() -> None:
    assert app_routes() == ROUTES


def test_open_routes_are_the_documented_few() -> None:
    assert {
        ("GET", "/health"),
        ("GET", "/auth/status"),
        ("POST", "/auth/login"),
        ("POST", "/auth/logout"),
    } == OPEN_ROUTES
    assert OPEN_ROUTES <= ROUTES


@pytest.fixture
def locked(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("APP_PASSCODE", "correct horse battery")
    get_settings.cache_clear()
    with TestClient(create_app(startup=False), base_url=APP_BASE_URL, headers=APP_HEADERS) as c:
        yield c
    get_settings.cache_clear()


@pytest.mark.parametrize(("method", "path"), sorted(ROUTES - OPEN_ROUTES))
def test_locked_app_refuses_every_other_route(locked: TestClient, method: str, path: str) -> None:
    r = locked.request(method, concrete(path), json={})
    assert r.status_code == 401, (method, path, r.text)
    assert r.json()["locked"] is True


@pytest.mark.parametrize("path", sorted(DOCS))
def test_locked_app_hides_the_api_docs(locked: TestClient, path: str) -> None:
    assert locked.get(path).status_code == 401


@pytest.mark.parametrize(("method", "path"), sorted(r for r in ROUTES if r[0] in STATE_CHANGING))
def test_every_state_changing_route_is_behind_the_csrf_guard(method: str, path: str) -> None:
    """No Origin and no X-Escalate-Request: refused before routing, for every route."""
    with TestClient(create_app(startup=False), base_url=APP_BASE_URL) as raw:
        r = raw.request(method, concrete(path), json={"confirm": True})
    assert r.status_code == 403, (method, path)
