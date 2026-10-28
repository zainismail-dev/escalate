"""A full offline environment for graph tests: file DBs, FakeLLM, fake SMTP, manual scheduler."""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from escalate.agent import runner
from escalate.channels import override_channel
from escalate.channels.email_smtp import SmtpChannel
from escalate.config import Settings
from escalate.db import session as db_session
from escalate.db.models import Base, Case, Event
from escalate.llm import set_llm
from escalate.llm.client import Slot
from escalate.playbooks import loader
from tests.factories import LED_FACTS
from tests.fakes.fake_llm import FakeLLM
from tests.fakes.fake_smtp import FakeSMTP
from tests.fakes.manual_scheduler import ManualScheduler


def echo_template(prompt: str, _slot: Slot) -> dict[str, str]:
    """The fake 'smart model' returns the rendered template unchanged (facts only)."""
    block = prompt.split("keep its structure:", 1)[1].split("Facts you may use", 1)[0]
    m = re.search(r"SUBJECT: (.*)\n", block)
    subject = m.group(1) if m else ""
    body = block.split("\n", 2)[2] if m else block
    return {"subject": subject, "body": body.strip()}


def facts_reply(facts: dict[str, str]) -> dict[str, Any]:
    return {"facts": {k: {"value": v, "confidence": 0.9} for k, v in facts.items()}}


def make_llm(
    facts: dict[str, str] | None = None,
    classification: dict[str, Any] | None = None,
    verdict: dict[str, Any] | None = None,
) -> FakeLLM:
    cls = {
        "case_type": "refund_refused",
        "country": "PK",
        "region": "PK-SD",
        "language": "en",
        "urgent": False,
        "reason": "refund refused",
    }
    cls.update(classification or {})
    return FakeLLM(
        rules=[
            ("You extract facts", facts_reply(facts if facts is not None else LED_FACTS)),
            ("Classify this complaint", cls),
            ("You write the", echo_template),
            ("List every factual claim", {"unsupported": []}),
            (
                "A company replied",
                verdict
                or {
                    "verdict": "refused",
                    "promise": None,
                    "promise_date": None,
                    "reason": "refused",
                },
            ),
        ]
    )


@dataclass
class AgentEnv:
    tmp: Path
    llm: FakeLLM
    scheduler: ManualScheduler
    settings: Settings

    def session(self) -> Session:
        return db_session.session_factory()()

    def event_types(self, case_id: int) -> list[str]:
        with self.session() as s:
            return list(
                s.scalars(select(Event.type).where(Event.case_id == case_id).order_by(Event.id))
            )

    def case(self, case_id: int) -> Case:
        s = self.session()
        case = s.get(Case, case_id)
        assert case is not None
        return case

    def new_case(self, **fields: Any) -> int:
        with db_session.session_scope() as s:
            case = Case(**fields)
            s.add(case)
            s.flush()
            return case.id


@pytest.fixture
def agent_env(tmp_path: Path, settings: Settings) -> Iterator[AgentEnv]:
    engine = db_session.configure(f"sqlite:///{tmp_path / 'app.db'}")
    Base.metadata.create_all(engine)
    loader.clear_cache()
    llm = make_llm()
    set_llm(llm)
    runner.configure(tmp_path / "checkpoints.db")
    sched = ManualScheduler(f"sqlite:///{tmp_path / 'jobs.db'}")
    sched.start()
    runner.set_scheduler(sched)
    FakeSMTP.reset()
    smtp_settings = settings.model_copy(
        update={"smtp_user": "ali@example.com", "smtp_app_password": "app-pw"}
    )
    override_channel("email", SmtpChannel(smtp_settings, smtp_factory=FakeSMTP))
    try:
        yield AgentEnv(tmp_path, llm, sched, settings)
    finally:
        override_channel("email", None)
        runner.set_scheduler(None)
        sched.shutdown()
        set_llm(None)
        engine.dispose()
