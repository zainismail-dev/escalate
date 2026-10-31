"""`make invite`: escalate.admin against the hosted database."""

from pathlib import Path

import pytest
from sqlalchemy import Engine

from escalate import admin
from escalate.db.models import Invite
from escalate.db.session import session_scope
from tests.hosted.conftest import PG_URL


@pytest.fixture
def pg_or_sqlite(hosted_db: Engine, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The CLI rebinds the engine to DATABASE_URL: on SQLite runs, keep the test engine."""
    if not PG_URL:
        monkeypatch.setattr(admin, "database_url", lambda: "postgresql://unused")
        monkeypatch.setattr(admin, "_bind", lambda _url: None)


def test_invite_uninvite_and_list(pg_or_sqlite: None, capsys: pytest.CaptureFixture[str]) -> None:
    assert admin.main(["invite", "  Alice@Example.com "]) == 0
    assert admin.main(["invite", "alice@example.com"]) == 0
    with session_scope() as s:
        assert [i.email for i in s.query(Invite)] == ["alice@example.com"]
    admin.main(["invites"])
    assert admin.main(["uninvite", "ALICE@example.com"]) == 0
    out = capsys.readouterr().out
    assert "invited alice@example.com" in out and "already invited" in out
    assert "removed alice@example.com" in out


@pytest.mark.parametrize("bad", ["not-an-email", "a@b@c", "", "x" * 400 + "@example.com"])
def test_bad_emails_are_refused(pg_or_sqlite: None, bad: str) -> None:
    with pytest.raises(SystemExit):
        admin.main(["invite", bad])


def test_a_non_postgres_url_asks_for_the_connection_string_hidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./escalate.db")
    from escalate.config import get_settings

    get_settings.cache_clear()
    asked: list[str] = []
    monkeypatch.setattr(admin.getpass, "getpass", lambda prompt: asked.append(prompt) or "nope")
    with pytest.raises(SystemExit, match="not a postgresql"):
        admin.database_url()
    assert "hidden" in asked[0]
    get_settings.cache_clear()
