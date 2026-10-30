"""Third review I1: the anti-harassment limit compared recipients literally, so "+tag", case
and Gmail dots made one mailbox look like many, and deleting cases reset the count."""

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from escalate.agent.draft import draft_step
from escalate.db.models import CaseFact, RecipientContact
from escalate.playbooks.loader import get_playbook
from escalate.safety import HarassmentPattern, normalise_recipient
from tests.factories import approve_as_user, led_case

PB = "intl-generic-refund-refused"


@pytest.mark.parametrize(
    ("raw", "normal"),
    [
        ("Support@Example.com", "support@example.com"),
        ("support+case42@example.com", "support@example.com"),
        ("Sup.Port+x@googlemail.com", "support@gmail.com"),
        ("s.u.p.p.o.r.t@gmail.com", "support@gmail.com"),
        ("first.last@example.com", "first.last@example.com"),  # dots matter outside Gmail
        ("  12 High St,\n London  ", "12 high st, london"),  # a postal address
    ],
)
def test_normalise_recipient(raw: str, normal: str) -> None:
    assert normalise_recipient(raw) == normal


def _write(db: Session, contact: str) -> object:
    pb = get_playbook(PB)
    case = led_case(db)
    fact = db.scalars(
        select(CaseFact).where(CaseFact.case_id == case.id, CaseFact.key == "seller_contact")
    ).one()
    fact.value = contact
    db.flush()
    db.refresh(case)
    return draft_step(db, case, pb, pb.steps[0], use_llm=False)


def test_address_variants_count_as_one_recipient(db: Session) -> None:
    for contact in ("victim@gmail.com", "Vic.Tim+1@gmail.com", "victim+2@googlemail.com"):
        approve_as_user(db, _write(db, contact).id)  # type: ignore[attr-defined]
    fourth = _write(db, "V.I.C.T.I.M+4@GMAIL.com")
    with pytest.raises(HarassmentPattern):
        approve_as_user(db, fourth.id)  # type: ignore[attr-defined]


def test_deleting_cases_does_not_reset_the_limit(db: Session) -> None:
    for _ in range(3):
        msg = _write(db, "victim@example.com")
        approve_as_user(db, msg.id)  # type: ignore[attr-defined]
        db.delete(msg.case)  # type: ignore[attr-defined]
        db.flush()
    fourth = _write(db, "victim@example.com")
    with pytest.raises(HarassmentPattern):
        approve_as_user(db, fourth.id)  # type: ignore[attr-defined]


def test_only_hashes_are_kept(db: Session) -> None:
    approve_as_user(db, _write(db, "victim@example.com").id)  # type: ignore[attr-defined]
    rows = db.scalars(select(RecipientContact)).all()
    assert len(rows) == 1
    stored = f"{rows[0].recipient_hash}{rows[0].case_hash}"
    assert "victim" not in stored and "example" not in stored
    assert len(rows[0].recipient_hash) == 64 and len(rows[0].case_hash) == 64


def test_recipient_contacts_migration_up_and_down(tmp_path: Path) -> None:
    import sqlalchemy as sa
    from alembic import command
    from alembic.config import Config

    repo = Path(__file__).resolve().parents[2]
    url = f"sqlite:///{tmp_path / 'm.db'}"
    cfg = Config(str(repo / "alembic.ini"))
    cfg.attributes["configure_logger"] = False
    cfg.set_main_option("script_location", str(repo / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = sa.create_engine(url)
    assert "recipient_contacts" in sa.inspect(engine).get_table_names()
    command.downgrade(cfg, "f42dcc77bddb")
    assert "recipient_contacts" not in sa.inspect(sa.create_engine(url)).get_table_names()
    engine.dispose()
