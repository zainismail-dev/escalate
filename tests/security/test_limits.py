"""Rate limits, body size, input bounds and generic error responses."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from escalate.api.limits import AI_PATHS
from escalate.api.main import create_app
from escalate.api.schemas import (
    AnswersIn,
    ApproveIn,
    CaseCreate,
    LanguageIn,
    MessageEdit,
    RejectIn,
    ReplyIn,
    SettingsIn,
    WithdrawIn,
)
from escalate.config import get_settings
from tests.factories import APP_BASE_URL, APP_HEADERS

FAKE = "00000000-0000-4000-8000-000000000000"


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch, db: Session) -> Iterator[TestClient]:
    monkeypatch.setenv("RATE_LIMIT_AI_PER_MINUTE", "3")
    monkeypatch.setenv("RATE_LIMIT_WRITES_PER_MINUTE", "5")
    monkeypatch.setenv("MAX_JSON_BODY_KB", "4")
    get_settings.cache_clear()
    with TestClient(create_app(startup=False), base_url=APP_BASE_URL, headers=APP_HEADERS) as c:
        yield c
    get_settings.cache_clear()


@pytest.mark.parametrize(
    "path",
    [
        "/cases/x/start",
        "/cases/x/answers",
        "/cases/x/replies",
        "/cases/x/retry",
        "/messages/x/approve",
        "/settings/llm-test",
    ],
)
def test_ai_endpoints_are_classified(path: str) -> None:
    assert AI_PATHS.match(path)


@pytest.mark.parametrize("path", ["/cases", "/cases/x", "/cases/x/evidence", "/settings"])
def test_plain_writes_are_not_ai(path: str) -> None:
    assert not AI_PATHS.match(path)


def test_ai_calls_are_rate_limited(api: TestClient) -> None:
    codes = [api.post(f"/cases/{FAKE}/retry").status_code for _ in range(4)]
    assert codes[:3] == [404, 404, 404] and codes[3] == 429
    r = api.post(f"/cases/{FAKE}/retry")
    assert r.headers["retry-after"] == "60"
    assert "too many AI requests" in r.json()["detail"]
    assert api.get("/cases").status_code == 200  # reads are not limited


def test_writes_are_rate_limited(api: TestClient) -> None:
    codes = [api.patch(f"/cases/{FAKE}", json={"title": "t"}).status_code for _ in range(6)]
    assert codes[-1] == 429 and 429 not in codes[:5]


def test_json_body_is_capped(api: TestClient) -> None:
    r = api.post("/cases", json={"description": "x" * 5000})
    assert r.status_code == 413


def test_streamed_body_without_length_is_capped(api: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        for _ in range(10):
            yield b"x" * 1024

    r = api.post("/cases", content=chunks(), headers={"Content-Type": "application/json"})
    assert r.status_code == 413


@pytest.mark.parametrize(
    ("model", "body"),
    [
        (CaseCreate, {"description": "a long enough text", "company": "x" * 201}),
        (CaseCreate, {"description": "a long enough text", "region": "x" * 11}),
        (CaseCreate, {"description": "x" * 20_001}),
        (AnswersIn, {"answers": {"k" * 65: "v"}}),
        (AnswersIn, {"answers": {"k": "v" * 2001}}),
        (AnswersIn, {"answers": {f"k{i}": "v" for i in range(101)}}),
        (RejectIn, {"reason": "x" * 2001}),
        (WithdrawIn, {"reason": "x" * 2001}),
        (ApproveIn, {"confirm": True, "recipient": "x" * 501}),
        (ApproveIn, {"confirm": True, "body": "x" * 50_001}),
        (MessageEdit, {"body": "x" * 50_001}),
        (ReplyIn, {"text": "x" * 50_001}),
        (SettingsIn, {"llm_api_key": "x" * 501}),
        (SettingsIn, {"llm_base_url": "http://" + "x" * 500}),
        (SettingsIn, {"model_smart": "x" * 201}),
        (LanguageIn, {"language": "x" * 36}),
    ],
)
def test_request_fields_are_bounded(model: type[BaseModel], body: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(body)


def test_every_request_string_has_an_upper_bound() -> None:
    """New request fields can't forget a bound: every str field has max_length or a Literal."""
    from escalate.api import schemas

    def unbounded(model: type[BaseModel]) -> list[str]:
        out = []
        for name, f in model.model_fields.items():
            text = repr(f.annotation)
            if "str" in text and "Literal" not in text:
                caps = [m for m in f.metadata if getattr(m, "max_length", None)]
                if not caps and "max_length" not in text:
                    out.append(f"{model.__name__}.{name}")
        return out

    inputs = [
        m
        for m in vars(schemas).values()
        if isinstance(m, type)
        and issubclass(m, BaseModel)
        and m.__name__.endswith(("In", "Create", "Edit", "Update"))
    ]
    assert inputs
    assert [n for m in inputs for n in unbounded(m)] == []


def test_query_strings_are_bounded(api: TestClient) -> None:
    assert api.get("/cases", params={"q": "x" * 201}).status_code == 422
    assert api.get("/checklist", params={"country": "../../etc"}).status_code == 422


def test_checklist_country_is_never_a_path() -> None:
    from escalate.agent.checklist import checklist_path

    generic = checklist_path(None)
    assert checklist_path("..") == generic
    assert checklist_path("../pk") == generic
    assert checklist_path("pk") != generic


def test_validation_errors_do_not_echo_input(api: TestClient) -> None:
    secret = "sk-live-0123456789abcdef"  # gitleaks:allow (a fake key)
    r = api.put("/settings", json={"llm_api_key": secret * 30, "smtp_port": "nope"})
    assert r.status_code == 422
    assert secret not in r.text
    assert set(r.json()["detail"][0]) == {"loc", "msg", "type"}


def test_unexpected_errors_are_generic(api: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    app = create_app(startup=False)
    boom = APIRouter()

    @boom.get("/boom")
    def _boom() -> None:
        raise RuntimeError("db password is hunter2 at /srv/escalate/secret.py line 3")

    app.include_router(boom)
    with TestClient(app, base_url=APP_BASE_URL, raise_server_exceptions=False) as c:
        r = c.get("/boom")
    assert r.status_code == 500
    body = r.json()
    assert set(body) == {"detail", "error_id"}
    assert "hunter2" not in r.text and "Traceback" not in r.text and "secret.py" not in r.text
    assert body["error_id"] in caplog.text  # the console has the details, by id


def test_api_responses_carry_security_headers(api: TestClient) -> None:
    for r in (api.get("/health"), api.get("/cases"), api.post("/cases", json={})):
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["x-frame-options"] == "DENY"
        assert r.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
        assert r.headers["cache-control"] == "no-store"
    assert "content-security-policy" not in api.get("/docs").headers  # Swagger UI's CDN
