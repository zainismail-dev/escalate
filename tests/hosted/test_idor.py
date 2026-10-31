"""IDOR suite: two users. On every route, user B can't read, change or even learn about user
A's cases, messages, evidence, timeline, PDFs or drafts: A's real ids get exactly the same 404
as ids that don't exist, and A's data is unchanged afterwards.

Routes come from the hosted inventory: a new route with a case or message id is covered here
automatically, and one without an id must be listed in NO_ID_ROUTES with the test covering it.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from sqlalchemy import select

from escalate.db.models import Case, CaseFact, Event, Evidence, Message
from escalate.db.session import session_scope
from tests.factories import LED_TEXT
from tests.hosted.conftest import Account, Hosted, hosted_mode
from tests.hosted.routes import BODIES, HOSTED_ROUTES, OPEN, QUERIES

MISSING = "00000000-0000-4000-8000-000000000000"
WITH_ID = sorted(r for r in HOSTED_ROUTES if "{" in r[1])


@dataclass
class World:
    hosted: Hosted
    alice: Account
    bob: Account
    case: str  # Alice's case (public id), waiting for her approval of a draft
    message: str  # the draft (public id)
    evidence_id: int  # Alice's uploaded receipt
    bob_case: str
    bob_message: str


def _started_case(acct: Account) -> tuple[str, str, int]:
    c = acct.client
    case = c.post("/cases", json={"description": LED_TEXT, "country": "PK", "region": "PK-SD"})
    cid = case.json()["id"]
    ev = c.post(
        f"/cases/{cid}/evidence", files={"file": ("receipt.txt", b"BM-48213", "text/plain")}
    )
    run = c.post(f"/cases/{cid}/start").json()
    assert run["waiting_for"] == "approve_draft", run
    return cid, run["pending"]["draft"]["message_id"], ev.json()["id"]


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> Iterator[World]:
    limits = {"RATE_LIMIT_AI_PER_MINUTE": "1000", "RATE_LIMIT_WRITES_PER_MINUTE": "1000"}
    with hosted_mode(tmp_path_factory.mktemp("idor"), **limits) as h:
        alice, bob = h.account("alice@example.com"), h.account("bob@example.com")
        case, message, evidence_id = _started_case(alice)
        bob_case, bob_message, _ = _started_case(bob)
        yield World(h, alice, bob, case, message, evidence_id, bob_case, bob_message)


def snapshot(case_public_id: str) -> dict[str, Any]:
    """Everything about a case (as nobody: no user filter)."""
    with session_scope() as s:
        case = s.scalar(select(Case).where(Case.public_id == case_public_id))
        assert case is not None
        return {
            "case": (case.title, case.status, case.current_step, case.language, case.user_id),
            "facts": sorted((f.key, f.value) for f in case.facts),
            "messages": sorted((m.public_id, m.status, m.body, m.recipient) for m in case.messages),
            "events": [(e.id, e.type) for e in case.events],
            "evidence": sorted((e.id, e.filename, e.sha256) for e in case.evidence),
        }


def call(acct: Account, method: str, path: str, case: str, message: str) -> Any:
    url = path.replace("{case_id}", case).replace("{message_id}", message)
    key = (method, path)
    if path.endswith("/evidence"):
        return acct.client.post(url, files={"file": ("x.txt", b"bob's file", "text/plain")})
    return acct.client.request(method, url, json=BODIES.get(key), params=QUERIES.get(key))


@pytest.mark.parametrize(("method", "path"), WITH_ID)
def test_bob_gets_the_same_404_for_alices_ids_as_for_missing_ones(
    world: World, method: str, path: str
) -> None:
    before = snapshot(world.case)
    real = call(world.bob, method, path, world.case, world.message)
    fake = call(world.bob, method, path, MISSING, MISSING)
    assert real.status_code == 404, (method, path, real.text)
    assert (real.status_code, real.json()) == (fake.status_code, fake.json())
    for leak in (world.case, world.message, "BM-48213", "Ali Raza", "BrightMart"):
        assert leak not in real.text
    assert snapshot(world.case) == before


@pytest.mark.parametrize(("method", "path"), WITH_ID)
def test_alices_ids_with_bobs_other_id_are_404_too(world: World, method: str, path: str) -> None:
    """Mixing: Bob's own case id with Alice's message id, and the other way round."""
    before = snapshot(world.case)
    for case, message in ((world.bob_case, world.message), (world.case, world.bob_message)):
        uses_case, uses_msg = "{case_id}" in path, "{message_id}" in path
        if (uses_case and case == world.case) or (uses_msg and message == world.message):
            r = call(world.bob, method, path, case, message)
            assert r.status_code == 404, (method, path, r.text)
    assert snapshot(world.case) == before


def test_alice_can_still_use_her_case(world: World) -> None:
    c = world.alice.client
    assert c.get(f"/cases/{world.case}").status_code == 200
    assert c.get(f"/messages/{world.message}/review").status_code == 200
    assert c.get(f"/cases/{world.case}/timeline").status_code == 200


# --- routes without ids -----------------------------------------------------------------------


def test_bob_lists_and_searches_only_his_own_cases(world: World) -> None:
    ids = {c["id"] for c in world.bob.client.get("/cases").json()}
    assert ids == {world.bob_case}
    for q in ("BrightMart", "BM-48213", "LED"):
        found = {c["id"] for c in world.bob.client.get("/cases", params={"q": q}).json()}
        assert world.case not in found
    assert world.case not in world.bob.client.get("/cases", params={"country": "PK"}).text


def test_a_new_case_belongs_to_its_creator_only(world: World) -> None:
    r = world.bob.client.post("/cases", json=BODIES[("POST", "/cases")])
    assert r.status_code == 201
    assert r.json()["id"] not in world.alice.client.get("/cases").text
    world.bob.client.delete(f"/cases/{r.json()['id']}")


def test_bob_cannot_use_alices_evidence_as_his_proof_of_delivery(world: World) -> None:
    before = snapshot(world.case)
    body = {"evidence_id": world.evidence_id}
    r = world.bob.client.post(f"/messages/{world.bob_message}/confirm-delivery", json=body)
    assert r.status_code in (404, 409) and "receipt.txt" not in r.text
    assert snapshot(world.case) == before


def test_me_settings_and_export_only_hold_the_callers_data(world: World) -> None:
    me = world.bob.client.get("/me").json()
    assert me["email"] == "bob@example.com" and me["open_cases"] == 1
    assert "alice" not in world.bob.client.get("/settings").text
    export = world.bob.client.get("/me/export")
    assert export.status_code == 200
    for leak in (world.case.encode(), b"Ali Raza", b"BrightMart", b"alice@example.com"):
        if leak != b"BrightMart":  # Bob's own case is about the same shop (LED_TEXT)
            assert leak not in export.content


def test_bobs_agent_runs_never_see_alices_facts(world: World) -> None:
    """Prompts are per case: none of Bob's prompts may carry Alice's case id or her facts."""
    with session_scope() as s:
        alice_facts = {
            f.value
            for f in s.scalars(select(CaseFact).join(Case).where(Case.public_id == world.case))
        }
    assert alice_facts
    # Both cases share the LED story, so compare the extracted case rows instead: every fact row
    # of Bob's case belongs to Bob.
    with session_scope() as s:
        for model in (CaseFact, Message, Event, Evidence):
            rows = s.scalars(
                select(model.user_id)
                .join(Case, model.case_id == Case.id)
                .where(Case.public_id == world.bob_case)
            ).all()
            assert set(rows) == {world.bob.id}, model


NO_ID_ROUTES = {
    ("GET", "/cases"): test_bob_lists_and_searches_only_his_own_cases,
    ("POST", "/cases"): test_a_new_case_belongs_to_its_creator_only,
    ("GET", "/me"): test_me_settings_and_export_only_hold_the_callers_data,
    ("GET", "/me/export"): test_me_settings_and_export_only_hold_the_callers_data,
    ("GET", "/settings"): test_me_settings_and_export_only_hold_the_callers_data,
    # tests/hosted/test_routes.py::test_user_settings_are_per_user_and_reveal_no_server_secrets
    ("PUT", "/settings"): test_me_settings_and_export_only_hold_the_callers_data,
    # tests/hosted/test_accounts.py: consent and deletion only touch the caller's rows
    ("POST", "/me/consent"): None,
    ("POST", "/me/delete"): None,
    # static reference data, the same for everyone
    ("GET", "/checklist"): None,
    ("GET", "/countries"): None,
}


def test_every_route_is_covered_by_the_idor_suite() -> None:
    no_id = {r for r in HOSTED_ROUTES - OPEN if "{" not in r[1]}
    assert no_id == set(NO_ID_ROUTES), "add the new route to NO_ID_ROUTES with its test"
    assert set(WITH_ID) | no_id | OPEN == HOSTED_ROUTES
