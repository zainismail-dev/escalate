from decimal import Decimal
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from escalate.db.events import log_event
from escalate.db.models import Case, CaseFact, CaseStatus, Event, Evidence, Message


def _full_case(db: Session) -> Case:
    case = Case(
        description="LED broke",
        case_type="refund_refused",
        country="PK",
        region="PK-SD",
        currency="PKR",
        amount=Decimal("45000.00"),
    )
    db.add(case)
    db.flush()
    ev = Evidence(case_id=case.id, kind="image", file_path="x.bin", sha256="0" * 64)
    db.add(ev)
    db.flush()
    db.add(CaseFact(case_id=case.id, key="order_id", value="A-1", source_evidence_id=ev.id))
    db.add(Message(case_id=case.id, step_id="s1", direction="out", channel="email", body="hi"))
    log_event(db, case.id, "case_created", {"by": "test"})
    db.commit()
    return case


def test_create_case_with_children(db: Session) -> None:
    case = _full_case(db)
    db.refresh(case)
    assert case.status == CaseStatus.INTAKE
    assert case.language == "en"
    assert case.fact_dict() == {"order_id": "A-1"}
    assert len(case.evidence) == 1
    assert case.messages[0].status == "draft"
    assert case.events[0].type == "case_created"
    assert case.events[0].payload == {"by": "test"}


def test_cascade_delete_removes_children(db: Session) -> None:
    case = _full_case(db)
    db.delete(case)
    db.commit()
    for model in (CaseFact, Evidence, Message, Event):
        assert db.scalars(select(model)).all() == []


def test_cascade_delete_at_sql_level(db: Session) -> None:
    case = _full_case(db)
    db.expunge_all()
    db.execute(Case.__table__.delete().where(Case.id == case.id))
    db.commit()
    assert db.scalars(select(Event)).all() == []


def test_no_country_or_currency_defaults(db: Session) -> None:
    case = Case(description="x")
    db.add(case)
    db.commit()
    assert case.country is None
    assert case.currency is None


def test_alembic_upgrade_creates_tables(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    tables = set(inspect(create_engine(url)).get_table_names())
    assert {"cases", "case_facts", "evidence", "messages", "events"} <= tables
