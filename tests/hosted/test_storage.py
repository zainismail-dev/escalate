"""Hosted evidence storage: encrypted before upload, server-generated keys under the owner's id,
read back only through the API, and a private bucket only."""

import json
import uuid

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from escalate.config import get_settings
from escalate.db.models import Evidence
from escalate.db.session import session_scope
from escalate.evidence.storage import (
    StorageError,
    SupabaseStorage,
    UnsafeObjectKey,
    check_key,
)
from tests.hosted.conftest import SUPABASE_URL, Hosted

A, B = str(uuid.uuid4()), str(uuid.uuid4())
RECEIPT = b"BrightMart receipt BM-48213, Rs 45,000"


def test_uploads_are_encrypted_and_keyed_under_the_owner(hosted: Hosted) -> None:
    alice = hosted.account("alice@example.com")
    cid = alice.client.post("/cases", json={"description": "x" * 30}).json()["id"]
    r = alice.client.post(
        f"/cases/{cid}/evidence", files={"file": ("../../../receipt.txt", RECEIPT, "text/plain")}
    )
    assert r.status_code == 201, r.text
    [key] = hosted.storage.keys_of(alice.id)
    check_key(key, alice.id)  # <user id>/<random>.bin, nothing from the upload's name
    blob = hosted.storage.objects[key]
    assert RECEIPT not in blob
    assert Fernet(get_settings().fernet_key.encode()).decrypt(blob) == RECEIPT
    with session_scope() as s:
        ev = s.scalar(select(Evidence))
        assert ev is not None and ev.file_path == key and ev.user_id == alice.id
    assert not (hosted.tmp / "evidence").exists()  # nothing on the API's (ephemeral) disk


def test_the_existing_upload_checks_still_apply(hosted: Hosted) -> None:
    alice = hosted.account("alice@example.com")
    cid = alice.client.post("/cases", json={"description": "x" * 30}).json()["id"]
    exe = alice.client.post(
        f"/cases/{cid}/evidence", files={"file": ("a.pdf", b"MZ\x90\x00binary", "application/pdf")}
    )
    assert exe.status_code == 415
    empty = alice.client.post(
        f"/cases/{cid}/evidence", files={"file": ("a.txt", b"", "text/plain")}
    )
    assert empty.status_code == 422
    assert hosted.storage.objects == {}


@pytest.mark.parametrize(
    "key",
    [
        f"{B}/{'a' * 32}.bin",  # another user's folder
        f"{A}/../{B}/{'a' * 32}.bin",
        f"{A}/{'a' * 32}.bin/../x",
        f"{A}/receipt.pdf",
        "/etc/passwd",
        f"{A.upper()}/{'a' * 32}.bin",
    ],
)
def test_only_generated_keys_in_the_owners_folder_are_used(key: str) -> None:
    with pytest.raises(UnsafeObjectKey):
        check_key(key, A)


def test_a_key_needs_an_owner() -> None:
    with pytest.raises(UnsafeObjectKey):
        check_key(f"{A}/{'a' * 32}.bin", None)


class Recorder:
    def __init__(self, responses: dict[tuple[str, str], httpx.Response] | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self.responses = responses or {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        for (method, prefix), resp in self.responses.items():
            if request.method == method and path.startswith(prefix):
                return resp
        if request.method == "GET" and "/object/" in path:
            return httpx.Response(200, content=b"blob")
        if path.endswith("/object/list/evidence"):
            return httpx.Response(200, json=[{"name": f"{'b' * 32}.bin"}])
        return httpx.Response(200, json={})


def storage(rec: Recorder) -> SupabaseStorage:
    client = httpx.Client(transport=httpx.MockTransport(rec))
    return SupabaseStorage(SUPABASE_URL, "service-key", "evidence", client=client)


def test_supabase_storage_requests() -> None:
    rec = Recorder()
    st = storage(rec)
    key = st.put(1, A, b"encrypted")
    assert st.get(key, 1, A) == b"blob"
    st.delete([key], 1, A)
    assert st.delete_user(A) == 1
    put, get, delete, listing, sweep = rec.requests
    assert put.method == "POST" and put.url.path == f"/storage/v1/object/evidence/{key}"
    assert put.headers["x-upsert"] == "false" and put.content == b"encrypted"
    assert get.url.path == f"/storage/v1/object/evidence/{key}"
    assert json.loads(delete.content) == {"prefixes": [key]}
    assert json.loads(listing.content)["prefix"] == A
    assert json.loads(sweep.content) == {"prefixes": [f"{A}/{'b' * 32}.bin"]}
    for req in rec.requests:
        assert req.headers["apikey"] == "service-key"
        assert req.headers["authorization"] == "Bearer service-key"
        assert req.url.host == "testproject.supabase.co"


def test_supabase_storage_refuses_another_users_key_before_any_request() -> None:
    rec = Recorder()
    with pytest.raises(UnsafeObjectKey):
        storage(rec).get(f"{B}/{'a' * 32}.bin", 1, A)
    assert rec.requests == []


def test_storage_errors_carry_no_response_body() -> None:
    body = {"error": "leaky", "key": "service-key"}
    rec = Recorder({("POST", "/storage/v1/object/"): httpx.Response(400, json=body)})
    with pytest.raises(StorageError) as exc:
        storage(rec).put(1, A, b"x")
    assert "leaky" not in str(exc.value) and "service-key" not in str(exc.value)


def test_a_public_bucket_refuses_to_start() -> None:
    rec = Recorder({("GET", "/storage/v1/bucket/"): httpx.Response(200, json={"public": True})})
    with pytest.raises(StorageError, match="public"):
        storage(rec).ensure_private_bucket()


def test_a_missing_bucket_is_created_private() -> None:
    rec = Recorder({("GET", "/storage/v1/bucket/"): httpx.Response(404, json={})})
    storage(rec).ensure_private_bucket()
    create = rec.requests[-1]
    assert create.url.path == "/storage/v1/bucket"
    assert json.loads(create.content) == {"id": "evidence", "name": "evidence", "public": False}
