"""Case titles: deterministic from facts, editable, backfilled by the migration."""

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from freezegun import freeze_time

from escalate.agent.titles import auto_title
from tests.agent_env import AgentEnv, agent_env  # noqa: F401
from tests.test_api import DAY0, _create, _started, client  # noqa: F401

REPO = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("case_type", "facts", "company", "expected"),
    [
        ("refund_refused", {"product": "43-inch LED TV"}, None, "43-inch LED TV — refund refused"),
        ("refund_refused", {"seller_name": "BrightMart"}, None, "Refund refused by BrightMart"),
        ("refund_refused", {}, "ShopCo", "Refund refused by ShopCo"),
        ("refund_refused", {}, None, "Refund refused"),
        (
            "subscription_cancel",
            {"plan_name": "monthly membership"},
            None,
            "Monthly membership still charging after cancelling",
        ),
        ("scam", {"payment_method": "UPI transfer"}, None, "Scam payment by UPI transfer"),
        ("scam", {"scammer_name": "Fast Courier"}, None, "Scam payment to Fast Courier"),
        ("scam", {}, None, "Suspected scam payment"),
        (None, {}, None, "Consumer complaint"),
    ],
)
def test_auto_title(
    case_type: str | None, facts: dict[str, str], company: str | None, expected: str
) -> None:
    assert auto_title(case_type, facts, company) == expected


def test_scam_title_is_never_just_scam() -> None:
    assert auto_title("scam", {}).lower() != "scam"


def test_long_facts_are_shortened_at_a_word() -> None:
    t = auto_title("refund_refused", {"product": "word " * 30})
    assert t.endswith("… — refund refused") and len(t) < 90


def test_title_set_at_intake_and_editable(client: TestClient) -> None:  # noqa: F811
    with freeze_time(DAY0):
        cid = _started(client)
    d = client.get(f"/cases/{cid}").json()
    assert d["title"] == "Refund refused by BrightMart Electronics"  # LED facts: no product
    r = client.patch(f"/cases/{cid}", json={"title": "  My   broken TV  "})
    assert r.status_code == 200 and r.json()["title"] == "My broken TV"
    assert client.get("/cases").json()[0]["title"] == "My broken TV"
    assert client.patch(f"/cases/{cid}", json={"title": "   "}).status_code == 422
    types = [e["type"] for e in client.get(f"/cases/{cid}/timeline").json()]
    assert types.count("title_set") == 2  # agent, then user


def test_new_case_has_a_title_before_intake(client: TestClient) -> None:  # noqa: F811
    assert _create(client)["title"] == "Consumer complaint"


def test_migration_backfills_and_downgrades(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    cfg = Config(str(REPO / "alembic.ini"))
    cfg.attributes["configure_logger"] = False
    cfg.set_main_option("script_location", str(REPO / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "e4a9cc27e4b4")  # before the title column
    engine = sa.create_engine(url)
    with engine.begin() as c:
        c.execute(
            sa.text(
                "INSERT INTO cases (id, description, case_type, language, status, created_at)"
                " VALUES (1, 'x', 'scam', 'en', 'intake', '2026-10-01'),"
                " (2, 'y', NULL, 'en', 'intake', '2026-10-01')"
            )
        )
        c.execute(
            sa.text(
                "INSERT INTO case_facts (case_id, key, value, confidence)"
                " VALUES (1, 'payment_method', 'UPI transfer', 1.0)"
            )
        )
    command.upgrade(cfg, "head")
    with engine.connect() as c:
        rows = dict(c.execute(sa.text("SELECT id, title FROM cases")).all())
    assert rows == {1: "Scam payment by UPI transfer", 2: None}
    command.downgrade(cfg, "e4a9cc27e4b4")
    with engine.connect() as c:
        cols = [r[1] for r in c.execute(sa.text("PRAGMA table_info(cases)"))]
    assert "title" not in cols
    engine.dispose()
