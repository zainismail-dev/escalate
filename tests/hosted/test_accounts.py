"""Hosted accounts: waitlist, consent, "Export my data" and "Delete my account"."""

import io
import json
import zipfile

from sqlalchemy import select

from escalate.agent import runner
from escalate.db.models import Base, Case, Invite, User
from escalate.db.session import session_scope
from tests.hosted.conftest import Hosted, count_rows
from tests.hosted.test_sending import started

USER_TABLES = ("cases", "case_facts", "evidence", "messages", "events", "user_settings")


def test_the_waitlist_stores_nothing_about_the_user(hosted: Hosted) -> None:
    waiting = hosted.account("waiting@example.com", invited=False)
    assert waiting.client.get("/me").json()["invited"] is False
    assert waiting.client.get("/cases").json()["waitlist"] is True
    assert count_rows(hosted.engine, "users") == 0


def test_consent_unlocks_the_case_routes(hosted: Hosted) -> None:
    new = hosted.account("new@example.com", consented=False)
    assert new.client.get("/cases").json()["consent_required"] is True
    assert new.client.post("/me/consent", json={"confirm": False}).status_code == 422
    me = new.client.post("/me/consent", json={"confirm": True}).json()
    assert me["consented"] is True and me["invited"] is True
    assert new.client.get("/cases").status_code == 200


def test_the_invite_is_matched_case_insensitively(hosted: Hosted) -> None:
    acct = hosted.account("carol@example.com")
    shouty = hosted.client(hosted.signer.token(acct.id, "Carol@Example.COM"))
    assert shouty.get("/cases").status_code == 200


def test_export_holds_the_users_data_only(hosted: Hosted) -> None:
    alice, bob = hosted.account("alice@example.com"), hosted.account("bob@example.com")
    a_case, _ = started(alice)
    started(bob)
    r = alice.client.get("/me/export")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert "attachment" in r.headers["content-disposition"]
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    data = json.loads(zf.read("data.json"))
    assert data["account"]["email"] == "alice@example.com"
    assert [c["public_id"] for c in data["cases"]] == [a_case]
    case = data["cases"][0]
    assert case["facts"] and case["messages"] and case["timeline"] and case["evidence"]
    for row in [case, *case["facts"], *case["messages"], *case["evidence"]]:
        assert not {"user_id", "file_path", "id"} & row.keys()
    evidence = [n for n in zf.namelist() if n.startswith("evidence/")]
    assert evidence == [f"evidence/{a_case}/1-r.txt"]
    assert zf.read(evidence[0]) == b"BM-48213"  # decrypted, as uploaded
    assert b"bob@example.com" not in zf.read("data.json")


def test_delete_my_account_needs_the_word_delete(hosted: Hosted) -> None:
    alice = hosted.account("alice@example.com")
    for body in ({}, {"confirm": True}, {"confirm": "delete"}, {"confirm": "DELETE "}):
        assert alice.client.post("/me/delete", json=body).status_code == 422
    assert hosted.admin.deleted == []


def test_delete_my_account_removes_everything_and_nothing_of_others(hosted: Hosted) -> None:
    alice, bob = hosted.account("alice@example.com"), hosted.account("bob@example.com")
    a_case, _ = started(alice)
    b_case, _ = started(bob)
    alice.client.put("/settings", json={"default_country": "GB"})
    with session_scope() as s:
        a_pk = s.scalar(select(Case.id).where(Case.public_id == a_case))
    assert a_pk is not None and runner.pending(a_pk) is not None
    assert hosted.storage.keys_of(alice.id)

    assert alice.client.post("/me/delete", json={"confirm": "DELETE"}).status_code == 204

    with session_scope() as s:
        for name in USER_TABLES:
            t = Base.metadata.tables[name]
            assert s.execute(select(t).where(t.c.user_id == alice.id)).first() is None, name
        assert s.get(User, alice.id) is None
        assert s.get(Invite, "alice@example.com") is None
    assert runner.pending(a_pk) is None  # the agent checkpoint is gone
    assert hosted.storage.keys_of(alice.id) == []
    assert hosted.admin.deleted == [alice.id]
    # Bob is untouched
    assert bob.client.get(f"/cases/{b_case}").status_code == 200
    assert hosted.storage.keys_of(bob.id)
    # the old token now only reaches the waitlist, and no row comes back
    assert alice.client.get("/cases").json()["waitlist"] is True
    assert alice.client.get("/me").json()["invited"] is False
    with session_scope() as s:
        assert s.get(User, alice.id) is None


def test_delete_sweeps_objects_left_by_an_interrupted_upload(hosted: Hosted) -> None:
    alice = hosted.account("alice@example.com")
    stray = hosted.storage.put(0, alice.id, b"orphan")
    assert alice.client.post("/me/delete", json={"confirm": "DELETE"}).status_code == 204
    assert stray not in hosted.storage.objects
