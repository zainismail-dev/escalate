"""Hosted mode's /settings: a user's own defaults only. The AI provider, models and email are
the server's (404 for any attempt to change them)."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from escalate import __version__
from escalate.api.deps import get_session, identity
from escalate.api.schemas import SettingsIn, SettingsOut
from escalate.config import get_settings
from escalate.hosted.accounts import user_settings
from escalate.i18n.countries import default_letter_language

router = APIRouter(tags=["system"])
USER_FIELDS = frozenset({"default_country", "default_language"})


def hosted_settings_out(session: Session, request: Request) -> SettingsOut:
    s = get_settings()
    prefs = user_settings(session, identity(request).user_id)
    return SettingsOut(
        llm_base_url="",
        model_smart="",
        model_fast="",
        has_llm_api_key=False,
        is_cloud=True,
        email_mode="user",
        smtp_host="",
        smtp_port=0,
        smtp_user="",
        has_smtp_password=False,
        default_country=prefs.default_country or s.default_country,
        default_language=prefs.default_language or default_letter_language(),
        enabled_letter_languages=s.enabled_letter_languages,
        demo_mode=False,
        version=__version__,
    )


@router.get("/settings", response_model=SettingsOut)
def read_settings(request: Request, session: Session = Depends(get_session)) -> SettingsOut:
    return hosted_settings_out(session, request)


@router.put("/settings", response_model=SettingsOut)
def save_settings(
    body: SettingsIn, request: Request, session: Session = Depends(get_session)
) -> SettingsOut:
    update = body.model_dump(exclude_unset=True)
    if update.keys() - USER_FIELDS:  # the AI provider and email can't be changed here
        raise HTTPException(404, "Not Found")
    prefs = user_settings(session, identity(request).user_id)
    if "default_country" in update:
        prefs.default_country = (update["default_country"] or "").upper() or None
    if "default_language" in update:
        prefs.default_language = update["default_language"] or None
    session.commit()
    return hosted_settings_out(session, request)
