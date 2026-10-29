"""Second review N2: an allowed LLM endpoint answered 307 to an internal address; the client
followed it (with the API key) and /settings/llm-test echoed the internal page back."""

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from escalate.api.main import create_app
from escalate.config import get_settings
from escalate.llm import set_llm
from tests.factories import APP_BASE_URL, APP_HEADERS

SECRET = "TOP-SECRET-INTERNAL-PAGE"


def _serve(handler: type[BaseHTTPRequestHandler]) -> tuple[HTTPServer, int]:
    server = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


@pytest.fixture
def internal() -> Iterator[tuple[int, list[str]]]:
    """The "internal" service the attacker wants to reach; records every hit."""
    hits: list[str] = []

    class Internal(BaseHTTPRequestHandler):
        def _answer(self) -> None:
            hits.append(f"{self.command} {self.path} key={self.headers.get('Authorization')}")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(f'{{"secret": "{SECRET}"}}'.encode())

        do_GET = do_POST = _answer

        def log_message(self, *_: object) -> None:
            pass

    server, port = _serve(Internal)
    yield port, hits
    server.shutdown()


@pytest.fixture
def redirector(internal: tuple[int, list[str]]) -> Iterator[int]:
    """The configured LLM endpoint: answers every request with 307 to the internal service."""
    target_port = internal[0]

    class Redirect(BaseHTTPRequestHandler):
        def _answer(self) -> None:
            self.send_response(307)
            self.send_header("Location", f"http://127.0.0.1:{target_port}/internal{self.path}")
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_GET = do_POST = _answer

        def log_message(self, *_: object) -> None:
            pass

    server, port = _serve(Redirect)
    yield port
    server.shutdown()


def test_llm_client_never_follows_a_redirect_to_an_internal_address(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
    redirector: int,
    internal: tuple[int, list[str]],
) -> None:
    monkeypatch.setenv("LLM_BASE_URL", f"http://127.0.0.1:{redirector}/v1")
    monkeypatch.setenv("LLM_API_KEY", "sk-test-not-for-internal-eyes")  # gitleaks:allow
    monkeypatch.setenv("MODEL_SMART", "m")
    monkeypatch.setenv("MODEL_FAST", "m")
    get_settings.cache_clear()
    set_llm(None)  # a real client built from these settings
    try:
        with TestClient(create_app(startup=False), base_url=APP_BASE_URL, headers=APP_HEADERS) as c:
            r = c.post("/settings/llm-test")
    finally:
        set_llm(None)
        get_settings.cache_clear()
    assert r.status_code == 200
    out = r.json()
    assert out["ok"] is False
    assert out["error"] == "the endpoint answered HTTP 307"
    assert SECRET not in r.text
    assert internal[1] == []  # the internal service was never reached (nor saw the key)


@pytest.mark.parametrize(
    ("exc", "shown"),
    [
        ("status", "the endpoint answered HTTP 500"),
        ("connection", "connection failed"),
        ("other", "the model test failed"),
    ],
)
def test_llm_test_errors_never_include_the_response(exc: str, shown: str) -> None:
    import httpx
    import openai

    from escalate.api.routes.system import llm_test_error

    req = httpx.Request("POST", "http://x/v1/chat/completions")
    errors = {
        "status": openai.InternalServerError(
            SECRET, response=httpx.Response(500, request=req, text=SECRET), body=SECRET
        ),
        "connection": openai.APIConnectionError(message=SECRET, request=req),
        "other": RuntimeError(SECRET),
    }
    assert llm_test_error(errors[exc]) == shown
