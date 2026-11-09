"""INFO: evidence and event ids in API responses are UUIDs, never the internal integer keys, and
delivery proof is named by its public id (another user's is a 404 like a missing one)."""

import re
import uuid

from sqlalchemy import select

from escalate.db.models import CaseFact, Evidence
from escalate.db.session import session_scope
from escalate.db.tenancy import as_user
from tests.hosted.conftest import Hosted
from tests.hosted.test_sending import started

UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


def test_evidence_fact_and_event_ids_are_uuids(hosted: Hosted) -> None:
    alice = hosted.account("alice@example.com")
    cid, _draft = started(alice)
    case = alice.client.get(f"/cases/{cid}").json()
    assert case["evidence"] and all(UUID.match(e["id"]) for e in case["evidence"])
    evidence_ids = {e["id"] for e in case["evidence"]}
    with as_user(alice.id), session_scope() as s:  # a fact read from that evidence
        ev = s.scalars(select(Evidence)).one()
        s.scalars(select(CaseFact)).first().source_evidence_id = ev.id  # type: ignore[union-attr]
    facts = alice.client.get(f"/cases/{cid}").json()["facts"]
    cited = [f["source_evidence_id"] for f in facts if f["source_evidence_id"]]
    assert cited == [next(iter(evidence_ids))]
    events = alice.client.get(f"/cases/{cid}/timeline").json()
    assert events and all(UUID.match(e["id"]) for e in events)
    added = [e for e in events if e["type"] == "evidence_added"]
    assert added and all(e["payload"]["evidence_id"] in evidence_ids for e in added)


def test_delivery_proof_is_named_by_public_id_and_scoped_to_the_user(hosted: Hosted) -> None:
    alice, bob = hosted.account("alice@example.com"), hosted.account("bob@example.com")
    cid, draft = started(alice)
    _bob_case, _ = started(bob)
    bob_evidence = bob.client.get(f"/cases/{_bob_case}").json()["evidence"][0]["id"]
    mid = draft["message_id"]
    approve = {"confirm": True, "recipient": draft["recipient"]}
    assert alice.client.post(f"/messages/{mid}/approve", json=approve).status_code == 200
    for bad in (bob_evidence, str(uuid.uuid4()), "1"):
        r = alice.client.post(f"/messages/{mid}/confirm-delivery", json={"evidence_id": bad})
        assert r.status_code == 404, bad
    own = alice.client.get(f"/cases/{cid}").json()["evidence"][0]["id"]
    r = alice.client.post(f"/messages/{mid}/confirm-delivery", json={"evidence_id": own})
    assert r.status_code == 200, r.text
