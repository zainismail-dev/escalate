"""Every owned row gets its user; while a user is current, no query sees another user's rows."""

from sqlalchemy import Engine, delete, select, update
from sqlalchemy.orm import Session

from escalate.db import session as db_session
from escalate.db.events import log_event
from escalate.db.models import Case, CaseFact, Event, Message
from escalate.db.tenancy import as_user, current_user_id

A, B = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"


def _case_with_children(user: str) -> int:
    with as_user(user), db_session.session_scope() as s:
        case = Case(description=f"{user} case", country="GB")
        s.add(case)
        s.flush()
        s.add(CaseFact(case_id=case.id, key="order_id", value=f"{user[:4]}-1"))
        s.add(Message(case_id=case.id, step_id="s1", direction="out", channel="email", body="b"))
        log_event(s, case.id, "case_created", {})
        return case.id


def test_new_rows_are_stamped_with_the_owner(hosted_db: Engine) -> None:
    cid = _case_with_children(A)
    with Session(hosted_db) as s:  # no current user: sees everything
        assert s.get(Case, cid).user_id == A  # type: ignore[union-attr]
        for model in (CaseFact, Message, Event):
            owners = set(s.scalars(select(model.user_id).where(model.case_id == cid)))
            assert owners == {A}, model


def test_a_child_written_without_a_current_user_still_gets_the_case_owner(
    hosted_db: Engine,
) -> None:
    """The scheduler tick or a runner step may write as nobody: the case decides."""
    cid = _case_with_children(A)
    assert current_user_id() is None
    with db_session.session_scope() as s:
        log_event(s, cid, "wait_expired", {})
    with Session(hosted_db) as s:
        assert set(s.scalars(select(Event.user_id).where(Event.case_id == cid))) == {A}


def test_queries_only_see_the_current_users_rows(hosted_db: Engine) -> None:
    a, b = _case_with_children(A), _case_with_children(B)
    with as_user(B), db_session.session_scope() as s:
        assert [c.id for c in s.scalars(select(Case))] == [b]
        assert s.get(Case, a) is None
        assert s.scalars(select(Message).where(Message.case_id == a)).all() == []
        assert s.scalars(select(CaseFact)).all() == s.get(Case, b).facts  # type: ignore[union-attr]
        assert {e.case_id for e in s.scalars(select(Event))} == {b}


def test_updates_and_deletes_cannot_reach_another_users_rows(hosted_db: Engine) -> None:
    a = _case_with_children(A)
    with as_user(B), db_session.session_scope() as s:
        s.execute(update(Case).values(title="pwned"))
        s.execute(delete(Message))
        s.execute(delete(Case).where(Case.id == a))
    with Session(hosted_db) as s:
        case = s.get(Case, a)
        assert case is not None and case.title is None
        assert len(case.messages) == 1


def test_local_mode_rows_have_no_owner_and_queries_are_unfiltered(db: Session) -> None:
    case = Case(description="local")
    db.add(case)
    db.flush()
    log_event(db, case.id, "case_created", {})
    db.commit()
    assert case.user_id is None and case.events[0].user_id is None
    assert db.scalars(select(Case)).all() == [case]


def test_hosted_lookups_without_a_user_fail_closed(hosted_db: Engine) -> None:
    import pytest

    from escalate.db import repo

    _case_with_children(A)
    with db_session.session_scope() as s, pytest.raises(repo.NoCurrentUser):
        repo.case_ids(s)
