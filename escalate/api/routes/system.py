"""Health, settings, countries, the scam checklist, privacy and demo data."""

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from escalate import __version__
from escalate.agent import runner
from escalate.agent.checklist import Checklist, load_checklist
from escalate.api.deps import get_session, public_case_id
from escalate.api.schemas import ConfirmIn, DemoOut, HealthOut, SettingsIn, SettingsOut
from escalate.config import SECRET_FIELDS, encrypt_secret, get_settings, settings_file
from escalate.db.models import Case
from escalate.db.session import session_scope
from escalate.i18n.countries import CountryOut, coverage, default_letter_language
from escalate.llm import get_llm, set_llm
from escalate.llm.privacy import is_cloud
from escalate.netguard import UnsafeEndpoint, check_host, check_url, url_host

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut(ok=True)


@router.get("/checklist", response_model=Checklist)
def checklist(country: str | None = Query(default=None, max_length=2)) -> Checklist:
    return load_checklist(country)


class LlmTestOut(BaseModel):
    ok: bool
    reply: str | None = None
    error: str | None = None


@router.post("/settings/llm-test", response_model=LlmTestOut)
def llm_test() -> LlmTestOut:
    try:
        reply = get_llm().complete("Reply with the single word: pong", slot="fast")
    except Exception as exc:  # show any connection/config problem to the user
        return LlmTestOut(ok=False, error=f"{type(exc).__name__}: {exc}")
    return LlmTestOut(ok=True, reply=reply.strip()[:200])


@router.get("/countries", response_model=list[CountryOut])
def countries() -> list[CountryOut]:
    """Every ISO 3166-1 country with its currency and local playbooks (if any)."""
    return coverage()


def settings_out() -> SettingsOut:
    s = get_settings()
    return SettingsOut(
        llm_base_url=s.llm_base_url,
        model_smart=s.model_smart,
        model_fast=s.model_fast,
        has_llm_api_key=bool(s.llm_api_key) and s.llm_api_key != "ollama",
        is_cloud=is_cloud(s),
        email_mode=s.email_mode,
        smtp_host=s.smtp_host,
        smtp_port=s.smtp_port,
        smtp_user=s.smtp_user,
        has_smtp_password=bool(s.smtp_app_password),
        default_country=s.default_country,
        default_language=default_letter_language(),
        enabled_letter_languages=s.enabled_letter_languages,
        demo_mode=s.demo_mode,
        version=__version__,
    )


@router.get("/settings", response_model=SettingsOut)
def read_settings() -> SettingsOut:
    """Current settings. Secrets are never returned, only whether they are set."""
    return settings_out()


@router.put("/settings", response_model=SettingsOut)
def save_settings(body: SettingsIn) -> SettingsOut:
    """Save to the settings file (it wins over `.env`). Omitted fields are unchanged; an empty
    string clears a value."""
    update = body.model_dump(exclude_unset=True)
    current = get_settings()
    try:
        if update.get("llm_base_url"):
            check_url(update["llm_base_url"], "LLM_BASE_URL")
        if update.get("smtp_host"):
            check_host(update["smtp_host"], "SMTP_HOST")
    except UnsafeEndpoint as exc:
        raise HTTPException(422, str(exc)) from exc
    path = settings_file()
    try:
        saved: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    if any(update.get(k) for k in SECRET_FIELDS) and not current.fernet_key:
        raise HTTPException(400, "set FERNET_KEY before saving an API key or app password")
    for key, value in update.items():
        if value in (None, ""):
            saved.pop(key, None)
        elif key in SECRET_FIELDS:  # never stored in plain text
            saved[key] = encrypt_secret(value, current.fernet_key)
        else:
            saved[key] = value.upper() if key == "default_country" else value
    # A secret belongs to its host: moving the host drops the stored secret (stored as "" so a
    # key from .env can't take its place) until the user enters it again for the new host.
    cleared: list[str] = []
    new_llm = update.get("llm_base_url")
    if (
        new_llm
        and url_host(new_llm) != url_host(current.llm_base_url)
        and not update.get("llm_api_key")
    ):
        saved["llm_api_key"], cleared = "", [*cleared, "llm_api_key"]
    new_smtp = update.get("smtp_host")
    if (
        new_smtp
        and new_smtp.lower() != current.smtp_host.lower()
        and not update.get("smtp_app_password")
    ):
        saved["smtp_app_password"], cleared = "", [*cleared, "smtp_app_password"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(saved, indent=2), encoding="utf-8")
    path.chmod(0o600)  # may hold an API key or app password
    get_settings.cache_clear()
    set_llm(None)  # the next call builds a client from the new settings
    out = settings_out()
    out.cleared_secrets = cleared
    return out


@router.post("/privacy/delete-all", status_code=204)
def delete_all(body: ConfirmIn, session: Session = Depends(get_session)) -> Response:
    """Delete every case: evidence files, drafts, timeline and scheduled reminders.
    Body must be {"confirm": true}."""
    ids = list(session.scalars(select(Case.id)))
    session.close()
    for cid in ids:
        runner.delete_case(cid)
    return Response(status_code=204)


@router.post("/demo/seed", response_model=DemoOut, status_code=201)
def demo_seed() -> DemoOut:
    """Four fictional cases in four countries, for trying the app. Nothing is sent."""
    if not get_settings().allow_demo_seed:
        raise HTTPException(403, "demo data is turned off (ALLOW_DEMO_SEED=false)")
    from escalate.demo import seed

    ids = seed()
    with session_scope() as s:
        return DemoOut(case_ids=[public_case_id(s, i) for i in ids])
