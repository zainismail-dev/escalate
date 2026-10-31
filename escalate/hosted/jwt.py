"""Supabase access tokens, verified on every API request (there are no API sessions).

A token is accepted only if all of these hold:
- its header names the pinned algorithm (SUPABASE_JWT_ALG, ES256 or RS256; never HS256 or
  "none") and a key id that is in the project's JWKS (fetched over https, cached);
- the signature verifies with that key;
- iss is <SUPABASE_URL>/auth/v1, aud is "authenticated", and exp, iat (and nbf, when present)
  are valid;
- it is a signed-in, non-anonymous user: role "authenticated", a UUID `sub`, and an email.
Anything else is a 401.
"""

import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

from escalate.config import Settings

LEEWAY_S = 10
MIN_REFETCH_S = 60  # an unknown key id refetches the JWKS at most once a minute


class AuthError(Exception):
    """Why a token was refused (for logs; clients only ever see "sign in required")."""


@dataclass(frozen=True)
class Identity:
    user_id: str  # Supabase auth user id (UUID)
    email: str  # lower-case


Fetch = Callable[[str], dict[str, Any]]


def fetch_jwks(url: str) -> dict[str, Any]:
    r = httpx.get(url, timeout=5, follow_redirects=False)
    r.raise_for_status()
    data: dict[str, Any] = r.json()
    return data


class Jwks:
    """The project's signing keys by key id, refreshed every `ttl` seconds."""

    def __init__(self, url: str, alg: str, ttl: int, fetch: Fetch | None = None) -> None:
        self.url, self.alg, self.ttl, self._fetch = url, alg, ttl, fetch
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at = -1e18
        self._lock = threading.Lock()

    def _refresh(self) -> None:
        keys = {}
        for k in (self._fetch or fetch_jwks)(self.url).get("keys", []):
            if not isinstance(k, dict) or not isinstance(k.get("kid"), str):
                continue
            if k.get("use", "sig") != "sig" or k.get("alg", self.alg) != self.alg:
                continue
            try:
                keys[k["kid"]] = jwt.PyJWK(k, algorithm=self.alg)
            except jwt.PyJWTError:
                continue  # a key of another type: never usable with the pinned algorithm
        self._keys, self._fetched_at = keys, time.monotonic()

    def key(self, kid: str) -> jwt.PyJWK:
        with self._lock:
            age = time.monotonic() - self._fetched_at
            if age > self.ttl or (kid not in self._keys and age > MIN_REFETCH_S):
                try:
                    self._refresh()
                except (httpx.HTTPError, ValueError) as exc:
                    raise AuthError("could not fetch the signing keys") from exc
            if kid not in self._keys:
                raise AuthError("unknown signing key")
            return self._keys[kid]


def verify(token: str, settings: Settings, jwks: Jwks) -> Identity:
    alg = settings.supabase_jwt_alg
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise AuthError("malformed token") from exc
    if header.get("alg") != alg:
        raise AuthError("unexpected algorithm")
    kid = header.get("kid")
    if not isinstance(kid, str) or not kid:
        raise AuthError("no key id")
    try:
        claims = jwt.decode(
            token,
            key=jwks.key(kid),
            algorithms=[alg],
            audience="authenticated",
            issuer=settings.supabase_issuer,
            leeway=LEEWAY_S,
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthError(type(exc).__name__) from exc
    return _identity(claims)


def _identity(claims: dict[str, Any]) -> Identity:
    if claims.get("role") != "authenticated" or claims.get("is_anonymous") is True:
        raise AuthError("not a signed-in user")
    sub, email = claims.get("sub"), claims.get("email")
    try:
        user_id = str(uuid.UUID(str(sub)))
    except ValueError as exc:
        raise AuthError("sub is not a user id") from exc
    if not isinstance(email, str) or "@" not in email or len(email) > 320:
        raise AuthError("no email")
    return Identity(user_id=user_id, email=email.strip().lower())
