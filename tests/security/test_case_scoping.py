"""Ids from one case can't be used on another (single user, but a planted id must not work)."""

from datetime import datetime

import pytest
from freezegun import freeze_time

from escalate.agent import runner
from escalate.db import session as db_session
from escalate.evidence.store import save_upload
from tests.agent_env import AgentEnv, agent_env, approve_pending  # noqa: F401
from tests.factories import LED_TEXT
from tests.test_pk_pack import FULL, make_llm


def test_proof_of_delivery_must_be_evidence_on_the_same_case(agent_env: AgentEnv) -> None:  # noqa: F811
    env = agent_env
    env.llm.rules[0] = ("You extract facts", make_llm(FULL).rules[0][1])
    with freeze_time(datetime(2026, 10, 1, 9)):
        cid = env.new_case(description=LED_TEXT, country="PK", region="PK-SD")
        other = env.new_case(description=LED_TEXT, country="PK", region="PK-SD")
        runner.start_case(cid)
        approve_pending(cid)
        runner.resume_with_reply(cid, "We refuse. Read our policy.")
        approve_pending(cid)  # the legal notice: posted, so proof of delivery is asked for
        with db_session.session_scope() as s:
            foreign = save_upload(s, other, "receipt.txt", b"another case", env.settings).id
            mine = save_upload(s, cid, "tcs.txt", b"TCS receipt", env.settings).id
        with pytest.raises(runner.RunnerError, match="not evidence on this case"):
            runner.confirm_delivery(cid, foreign)
        with pytest.raises(runner.RunnerError, match="not evidence on this case"):
            runner.confirm_delivery(cid, 987654)
        runner.confirm_delivery(cid, mine)  # its own evidence still works
