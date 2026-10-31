"""Hosted route inventory: who may call what, and what hosted mode does not serve at all."""

import pytest

from tests.hosted.conftest import Hosted
from tests.hosted.routes import BODIES, HOSTED_ROUTES, MEMBERS, OPEN, QUERIES, SIGNED_IN

FAKE = "00000000-0000-4000-8000-000000000000"


def concrete(path: str) -> str:
    return path.replace("{case_id}", FAKE).replace("{message_id}", FAKE)


def call(client, method: str, path: str):  # type: ignore[no-untyped-def]
    key = (method, path)
    if path.endswith("/evidence"):
        return client.post(concrete(path), files={"file": ("r.txt", b"receipt", "text/plain")})
    return client.request(method, concrete(path), json=BODIES.get(key), params=QUERIES.get(key))


def test_hosted_route_inventory_is_complete(hosted: Hosted) -> None:
    paths = hosted.app.openapi()["paths"]
    routes = {(m.upper(), p) for p, ops in paths.items() for m in ops}
    assert routes == HOSTED_ROUTES


@pytest.mark.parametrize(("method", "path"), sorted(HOSTED_ROUTES - OPEN))
def test_every_route_needs_a_valid_token(hosted: Hosted, method: str, path: str) -> None:
    r = call(hosted.client(), method, path)
    assert r.status_code == 401, (method, path, r.text)


@pytest.mark.parametrize(("method", "path"), sorted(MEMBERS))
def test_waitlisted_users_get_403_waitlist_on_every_case_route(
    hosted: Hosted, method: str, path: str
) -> None:
    waiting = hosted.account("waiting@example.com", invited=False)
    r = call(waiting.client, method, path)
    assert r.status_code == 403, (method, path, r.text)
    assert r.json()["waitlist"] is True


@pytest.mark.parametrize(("method", "path"), sorted(MEMBERS))
def test_invited_users_must_consent_first(hosted: Hosted, method: str, path: str) -> None:
    new = hosted.account("new@example.com", consented=False)
    r = call(new.client, method, path)
    assert r.status_code == 403, (method, path, r.text)
    assert r.json()["consent_required"] is True


def test_signed_in_routes_are_open_to_the_waitlist(hosted: Hosted) -> None:
    waiting = hosted.account("waiting@example.com", invited=False)
    assert ("GET", "/me") in SIGNED_IN
    me = waiting.client.get("/me").json()
    assert me["invited"] is False and me["consented"] is False
    assert waiting.client.get("/countries").status_code == 200
    r = waiting.client.post("/me/consent", json={"confirm": True})
    assert r.status_code == 403 and r.json()["waitlist"] is True


DISABLED = [
    ("POST", "/settings/llm-test"),  # Ollama / model checks
    ("POST", "/privacy/delete-all"),  # global delete: /me/delete instead
    ("POST", "/demo/seed"),
    ("GET", "/auth/status"),  # APP_PASSCODE
    ("POST", "/auth/login"),
    ("POST", "/auth/logout"),
    ("GET", "/docs"),
    ("GET", "/redoc"),
    ("GET", "/openapi.json"),
    ("GET", "/docs/oauth2-redirect"),
]


@pytest.mark.parametrize(("method", "path"), DISABLED)
def test_local_only_routes_are_404_in_hosted_mode(hosted: Hosted, method: str, path: str) -> None:
    alice = hosted.account("alice@example.com")
    r = alice.client.request(method, path, json={"confirm": True, "passcode": "x"})
    assert r.status_code == 404, (method, path, r.text)


@pytest.mark.parametrize(
    "field",
    [
        {"llm_base_url": "https://evil.example/v1"},
        {"llm_api_key": "sk-mine"},
        {"model_smart": "gpt"},
        {"smtp_host": "smtp.example.com"},
        {"smtp_user": "me@example.com"},
        {"smtp_app_password": "pw"},
        {"smtp_port": 25},
        {"default_country": "GB", "llm_base_url": "https://evil.example/v1"},
    ],
)
def test_provider_and_smtp_settings_cannot_be_changed(
    hosted: Hosted, field: dict[str, object]
) -> None:
    alice = hosted.account("alice@example.com")
    assert alice.client.put("/settings", json=field).status_code == 404


def test_user_settings_are_per_user_and_reveal_no_server_secrets(hosted: Hosted) -> None:
    alice, bob = hosted.account("alice@example.com"), hosted.account("bob@example.com")
    r = alice.client.put("/settings", json={"default_country": "gb"})
    assert r.status_code == 200 and r.json()["default_country"] == "GB"
    assert bob.client.get("/settings").json()["default_country"] is None
    text = alice.client.get("/settings").text
    for secret in ("test-groq-key", "groq.test", "app-pw", "owner@example.com", "service-role"):
        assert secret not in text
    case = alice.client.post("/cases", json={"description": "x" * 30}).json()
    assert case["country"] == "GB" and case["currency"] == "GBP"
