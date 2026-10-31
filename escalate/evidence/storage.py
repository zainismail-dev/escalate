"""Where encrypted evidence files live.

- Local mode: files under EVIDENCE_DIR (escalate/evidence/store.py, LocalStorage).
- Hosted mode: a private Supabase Storage bucket. Object keys are `<user id>/<random>.bin`,
  generated here (never from the upload's name). Every object is Fernet-encrypted before it
  leaves the API, and is only ever read back by the API after the evidence row's ownership
  check: the bucket has no public URLs and the browser never talks to it.
"""

import re
import secrets
import uuid
from typing import Protocol

import httpx

from escalate.hosted.supabase import service_headers


class StorageError(RuntimeError):
    """The storage service refused or failed (no details: they may echo keys)."""


class UnsafeObjectKey(ValueError):
    """A key that isn't one of ours, or isn't under its owner's folder."""


class Storage(Protocol):
    def put(self, case_id: int, user_id: str | None, blob: bytes) -> str:
        """Store an encrypted blob; return what Evidence.file_path should hold."""
        ...

    def get(self, file_path: str, case_id: int, user_id: str | None) -> bytes: ...

    def delete(self, file_paths: list[str], case_id: int, user_id: str | None) -> None: ...

    def delete_user(self, user_id: str) -> int:
        """Every object of the user (hosted account deletion)."""
        ...


KEY_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/[0-9a-f]{32}\.bin"
)


def object_key(user_id: str | None) -> str:
    return f"{_owner(user_id)}/{secrets.token_hex(16)}.bin"


def _owner(user_id: str | None) -> str:
    try:
        return str(uuid.UUID(str(user_id)))
    except ValueError as exc:
        raise UnsafeObjectKey("hosted evidence needs the owner's user id") from exc


def check_key(key: str, user_id: str | None) -> str:
    """`key` if it is a generated key inside `user_id`'s folder; otherwise raise."""
    if not KEY_RE.fullmatch(key) or not key.startswith(_owner(user_id) + "/"):
        raise UnsafeObjectKey("not an evidence object of this user")
    return key


class SupabaseStorage:
    """Supabase Storage's REST API with the service-role key (server side only)."""

    def __init__(
        self, url: str, service_key: str, bucket: str, client: httpx.Client | None = None
    ) -> None:
        self.base = f"{url.rstrip('/')}/storage/v1"
        self.bucket = bucket
        self.headers = service_headers(service_key)
        self.client = client or httpx.Client(timeout=60, follow_redirects=False)

    def _call(
        self, method: str, path: str, extra: dict[str, str] | None = None, **kw: object
    ) -> httpx.Response:
        headers = {**self.headers, **(extra or {})}
        try:
            r = self.client.request(method, f"{self.base}{path}", headers=headers, **kw)  # type: ignore[arg-type]
        except httpx.HTTPError as exc:
            raise StorageError(f"storage {method} failed: {type(exc).__name__}") from None
        if r.status_code >= 400:
            raise StorageError(f"storage {method} answered HTTP {r.status_code}")
        return r

    def put(self, case_id: int, user_id: str | None, blob: bytes) -> str:
        key = object_key(user_id)
        upload = {"Content-Type": "application/octet-stream", "x-upsert": "false"}
        self._call("POST", f"/object/{self.bucket}/{key}", upload, content=blob)
        return key

    def get(self, file_path: str, case_id: int, user_id: str | None) -> bytes:
        key = check_key(file_path, user_id)
        return self._call("GET", f"/object/{self.bucket}/{key}").content

    def delete(self, file_paths: list[str], case_id: int, user_id: str | None) -> None:
        keys = [check_key(p, user_id) for p in file_paths]
        for i in range(0, len(keys), 100):
            self._call("DELETE", f"/object/{self.bucket}", json={"prefixes": keys[i : i + 100]})

    def list_user(self, user_id: str) -> list[str]:
        """Every object key in the user's folder (account deletion sweeps leftovers too)."""
        owner, keys, offset = _owner(user_id), [], 0
        while True:
            r = self._call(
                "POST",
                f"/object/list/{self.bucket}",
                json={"prefix": owner, "limit": 1000, "offset": offset},
            )
            names = [o.get("name", "") for o in r.json() if isinstance(o, dict)]
            keys += [f"{owner}/{n}" for n in names if n]
            if len(names) < 1000:
                return keys
            offset += len(names)

    def delete_user(self, user_id: str) -> int:
        keys = [k for k in self.list_user(user_id) if KEY_RE.fullmatch(k)]
        self.delete(keys, 0, user_id)
        return len(keys)

    def ensure_private_bucket(self) -> None:
        """Create the bucket (private) if missing; refuse to run on a public one."""
        try:
            info = self._call("GET", f"/bucket/{self.bucket}").json()
        except StorageError:
            self._call(
                "POST", "/bucket", json={"id": self.bucket, "name": self.bucket, "public": False}
            )
            return
        if info.get("public") is not False:
            raise StorageError(f"the storage bucket {self.bucket!r} is public: make it private")
