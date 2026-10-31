"""Hosted mode: POST /internal/tick, called hourly by .github/workflows/tick.yml.

Protected by the X-Tick-Secret header (TICK_SECRET, compared in constant time). A missing or
wrong secret gets the same 404 as a route that doesn't exist.
"""

import hmac

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from escalate.config import MIN_TICK_SECRET, get_settings
from escalate.scheduler.tick import run_tick

router = APIRouter(prefix="/internal", tags=["internal"])
TICK_HEADER = "x-tick-secret"


class TickOut(BaseModel):
    woke: int
    skipped: int
    failed: int
    deadline_warnings: int


def tick_allowed(given: str | None) -> bool:
    secret = get_settings().tick_secret
    if not get_settings().hosted or len(secret) < MIN_TICK_SECRET or given is None:
        return False
    return hmac.compare_digest(given.encode(), secret.encode())


@router.post("/tick", response_model=TickOut)
def tick(request: Request) -> TickOut:
    if not tick_allowed(request.headers.get(TICK_HEADER)):
        raise HTTPException(404, "Not Found")
    return TickOut(**run_tick())
