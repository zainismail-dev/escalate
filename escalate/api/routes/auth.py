"""The optional app lock's endpoints (escalate/api/applock.py). Open even when locked."""

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from escalate.api.applock import COOKIE, AppLock, TooManyAttempts, session_token
from escalate.config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


class LockStatus(BaseModel):
    enabled: bool  # APP_PASSCODE is set
    unlocked: bool  # this browser has a valid session (always true when not enabled)


class LoginIn(BaseModel):
    passcode: str = Field(min_length=1, max_length=200)


def _lock(request: Request) -> AppLock:
    lock: AppLock = request.app.state.lock
    return lock


@router.get("/status", response_model=LockStatus)
def status(request: Request) -> LockStatus:
    lock = _lock(request)
    if not lock.enabled():
        return LockStatus(enabled=False, unlocked=True)
    return LockStatus(enabled=True, unlocked=lock.valid(session_token(request.scope["headers"])))


@router.post("/login", status_code=204)
def login(body: LoginIn, request: Request, response: Response) -> None:
    lock = _lock(request)
    if not lock.enabled():
        return
    client = request.client.host if request.client else "unknown"
    try:
        token = lock.login(body.passcode, client)
    except TooManyAttempts as exc:
        raise HTTPException(429, str(exc), headers={"Retry-After": "900"}) from exc
    if token is None:
        raise HTTPException(401, "wrong passcode")
    response.set_cookie(
        COOKIE,
        token,
        max_age=get_settings().app_session_hours * 3600,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
        path="/",
    )


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response) -> None:
    _lock(request).logout(session_token(request.scope["headers"]))
    response.delete_cookie(COOKIE, path="/", httponly=True, samesite="strict")
