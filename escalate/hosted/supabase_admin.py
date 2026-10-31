"""Supabase Auth's admin API with the service-role key (server side only): deleting a user."""

from typing import Protocol

import httpx

from escalate.config import get_settings


class AdminError(RuntimeError):
    pass


class Admin(Protocol):
    def delete_user(self, user_id: str) -> None: ...


class SupabaseAdmin:
    def __init__(self, url: str, service_key: str, client: httpx.Client | None = None) -> None:
        self.base = f"{url.rstrip('/')}/auth/v1/admin"
        self.headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}
        self.client = client or httpx.Client(timeout=20, follow_redirects=False)

    def delete_user(self, user_id: str) -> None:
        """Idempotent: an already deleted user is fine."""
        try:
            r = self.client.delete(f"{self.base}/users/{user_id}", headers=self.headers)
        except httpx.HTTPError as exc:
            raise AdminError(f"deleting the sign-in failed: {type(exc).__name__}") from None
        if r.status_code >= 400 and r.status_code != 404:
            raise AdminError(f"deleting the sign-in failed: HTTP {r.status_code}")


_override: Admin | None = None


def set_admin(admin: Admin | None) -> None:
    global _override
    _override = admin


def get_admin() -> Admin:
    if _override is not None:
        return _override
    s = get_settings()
    return SupabaseAdmin(s.supabase_url, s.supabase_service_role_key)
