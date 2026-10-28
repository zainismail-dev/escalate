"""Health, settings checks and the scam checklist."""

from fastapi import APIRouter
from pydantic import BaseModel

from escalate import __version__
from escalate.agent.checklist import Checklist, load_checklist
from escalate.api.schemas import HealthOut
from escalate.config import get_settings
from escalate.llm import get_llm
from escalate.llm.privacy import is_cloud

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    s = get_settings()
    return HealthOut(
        ok=True,
        version=__version__,
        is_cloud=is_cloud(s),
        llm_base_url=s.llm_base_url,
        demo_mode=s.demo_mode,
        email_mode=s.email_mode,
    )


@router.get("/checklist", response_model=Checklist)
def checklist(country: str | None = None) -> Checklist:
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
