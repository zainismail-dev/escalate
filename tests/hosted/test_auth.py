"""Supabase JWT verification: only a valid, signed-in user's token passes; everything else is a
401 with no detail. There are no API sessions (no cookies)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from escalate.config import get_settings
from escalate.hosted.jwt import AuthError, Jwks, verify
from tests.hosted.conftest import DROP, ISSUER, Hosted, Signer

UID = str(uuid.uuid4())
EMAIL = "alice@example.com"


def now() -> int:
    return int(datetime.now(UTC).timestamp())


def jwks_for(signer: Signer) -> Jwks:
    return Jwks(f"{ISSUER}/.well-known/jwks.json", "ES256", 600, fetch=signer.fetch)


def test_a_valid_token_gives_the_user(hosted_env: dict[str, str]) -> None:
    signer = Signer()
    ident = verify(signer.token(UID, "Alice@Example.com"), get_settings(), jwks_for(signer))
    assert ident.user_id == UID and ident.email == "alice@example.com"


def _claims() -> dict[str, Any]:
    return {
        "iss": ISSUER,
        "aud": "authenticated",
        "sub": UID,
        "email": EMAIL,
        "role": "authenticated",
        "iat": now(),
        "exp": now() + 600,
    }


def _hs256_with_public_key(signer: Signer) -> str:
    """Algorithm confusion: an HMAC token keyed with (a piece of) the public key."""
    pem = signer.key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return jwt.encode(_claims(), pem.hex(), algorithm="HS256", headers={"kid": signer.kid})


def _none_alg(signer: Signer) -> str:
    return jwt.encode(_claims(), None, algorithm="none", headers={"kid": signer.kid})


def _tampered(signer: Signer) -> str:
    head, _body, sig = signer.token(UID, EMAIL).split(".")
    other = signer.token(str(uuid.uuid4()), "mallory@example.com").split(".")[1]
    return f"{head}.{other}.{sig}"


BAD: dict[str, Any] = {
    "expired": lambda s: s.token(UID, EMAIL, exp=now() - 3600, iat=now() - 7200),
    "not yet valid (nbf)": lambda s: s.token(UID, EMAIL, nbf=now() + 3600),
    "issued in the future": lambda s: s.token(UID, EMAIL, iat=now() + 3600),
    "no exp": lambda s: s.token(UID, EMAIL, exp=DROP),
    "wrong issuer": lambda s: s.token(UID, EMAIL, iss="https://evil.supabase.co/auth/v1"),
    "wrong audience": lambda s: s.token(UID, EMAIL, aud="anon"),
    "no audience": lambda s: s.token(UID, EMAIL, aud=DROP),
    "anon role": lambda s: s.token(UID, EMAIL, role="anon"),
    "service_role": lambda s: s.token(UID, EMAIL, role="service_role"),
    "anonymous user": lambda s: s.token(UID, EMAIL, is_anonymous=True),
    "sub not a uuid": lambda s: s.token("admin", EMAIL),
    "no email": lambda s: s.token(UID, DROP),
    "unknown kid": lambda s: s.token(UID, EMAIL, headers={"kid": "someone-elses"}),
    "no kid": lambda s: jwt.encode(_claims(), s.key, algorithm="ES256"),
    "signed by another key, same kid": lambda s: s.token(
        UID, EMAIL, key=ec.generate_private_key(ec.SECP256R1())
    ),
    "RS256 (not the pinned algorithm)": lambda s: s.token(
        UID, EMAIL, alg="RS256", key=rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ),
    "HS256 algorithm confusion": _hs256_with_public_key,
    "alg none": _none_alg,
    "tampered payload": _tampered,
    "garbage": lambda s: "not-a-jwt",
    "empty": lambda s: "",
}


@pytest.mark.parametrize("case", sorted(BAD))
def test_bad_tokens_are_refused(hosted_env: dict[str, str], case: str) -> None:
    signer = Signer()
    with pytest.raises(AuthError):
        verify(BAD[case](signer), get_settings(), jwks_for(signer))


@pytest.mark.parametrize("case", sorted(BAD))
def test_bad_tokens_get_a_401_from_the_api(hosted: Hosted, case: str) -> None:
    hosted.account(EMAIL)
    r = hosted.client(BAD[case](hosted.signer)).get("/cases")
    assert r.status_code == 401, r.text
    assert r.json() == {"detail": "sign in required", "signed_in": False}
    assert r.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "header", ["", "Bearer", "Bearer ", "Basic dXNlcjpwYXNz", "Token abc", "bearer"]
)
def test_missing_or_malformed_authorization_is_a_401(hosted: Hosted, header: str) -> None:
    c = hosted.client()
    r = c.get("/cases", headers={"Authorization": header} if header else {})
    assert r.status_code == 401


def test_a_huge_token_is_refused_without_parsing(hosted: Hosted) -> None:
    assert hosted.client("x" * 9000).get("/cases").status_code == 401


def test_jwks_is_cached_and_an_unknown_kid_cannot_force_refetches(hosted: Hosted) -> None:
    acct = hosted.account(EMAIL)
    for _ in range(3):
        assert acct.client.get("/cases").status_code == 200
    for _ in range(5):
        bad = hosted.signer.token(acct.id, EMAIL, headers={"kid": uuid.uuid4().hex})
        assert hosted.client(bad).get("/cases").status_code == 401
    assert hosted.signer.fetches == 1


def test_jwks_refreshes_after_the_cache_time(hosted_env: dict[str, str]) -> None:
    signer = Signer()
    jwks = jwks_for(signer)
    jwks.key(signer.kid)
    jwks.key(signer.kid)
    assert signer.fetches == 1
    jwks._fetched_at -= timedelta(minutes=11).total_seconds()  # older than the 10 min TTL
    jwks.key(signer.kid)
    assert signer.fetches == 2


def test_jwks_keys_for_another_algorithm_are_ignored(hosted_env: dict[str, str]) -> None:
    signer = Signer()
    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rsa_jwk = {
        **jwt.algorithms.RSAAlgorithm.to_jwk(rsa_key.public_key(), as_dict=True),
        "kid": "rsa",
        "alg": "RS256",
    }
    jwks = Jwks("u", "ES256", 600, fetch=lambda _u: {"keys": [rsa_jwk, signer.jwk()]})
    with pytest.raises(AuthError, match="unknown signing key"):
        jwks.key("rsa")
    assert jwks.key(signer.kid)


def test_the_api_sets_no_cookies_and_cors_allows_only_the_web_origin(hosted: Hosted) -> None:
    acct = hosted.account(EMAIL)
    r = acct.client.get("/cases")
    assert r.status_code == 200 and "set-cookie" not in r.headers
    pre = {
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization",
    }
    ok = hosted.client().options("/cases", headers={"Origin": "https://beta.escalate.test", **pre})
    assert ok.headers["access-control-allow-origin"] == "https://beta.escalate.test"
    assert "authorization" in ok.headers["access-control-allow-headers"].lower()
    assert "access-control-allow-credentials" not in ok.headers
    evil = hosted.client().options("/cases", headers={"Origin": "https://evil.example", **pre})
    assert "access-control-allow-origin" not in evil.headers


def test_state_changes_still_need_the_web_origin(hosted: Hosted) -> None:
    acct = hosted.account(EMAIL)
    r = acct.client.post(
        "/cases", json={"description": "x" * 30}, headers={"Origin": "https://evil.example"}
    )
    assert r.status_code == 403
