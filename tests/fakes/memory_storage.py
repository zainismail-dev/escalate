"""Hosted-mode evidence storage in memory, with the real key rules (escalate/evidence/storage)."""

from escalate.evidence.storage import KEY_RE, check_key, object_key


class MemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, case_id: int, user_id: str | None, blob: bytes) -> str:
        key = object_key(user_id)
        self.objects[key] = blob
        return key

    def get(self, file_path: str, case_id: int, user_id: str | None) -> bytes:
        return self.objects[check_key(file_path, user_id)]

    def delete(self, file_paths: list[str], case_id: int, user_id: str | None) -> None:
        for p in file_paths:
            self.objects.pop(check_key(p, user_id), None)

    def delete_user(self, user_id: str) -> int:
        keys = [k for k in self.objects if k.startswith(user_id + "/") and KEY_RE.fullmatch(k)]
        for k in keys:
            del self.objects[k]
        return len(keys)

    def keys_of(self, user_id: str) -> list[str]:
        return [k for k in self.objects if k.startswith(user_id + "/")]


class FakeAdmin:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete_user(self, user_id: str) -> None:
        self.deleted.append(user_id)
