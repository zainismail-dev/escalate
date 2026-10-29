"""FastAPI app. The scheduler runs inside this process and starts with the app.

uv run uvicorn escalate.api.main:app --reload
"""

import logging
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import openai
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from escalate import __version__
from escalate.agent import runner
from escalate.agent.approval import ApprovalError, RecipientNotConfirmed, UnsupportedFacts
from escalate.api.applock import AppLock, AppLockGuard
from escalate.api.limits import RequestLimits
from escalate.api.routes import auth, cases, messages, system
from escalate.api.security import CSRF_HEADER, CsrfGuard, SecurityHeaders, split_list
from escalate.channels import NotApproved, ProofRequired
from escalate.channels.email_smtp import EmailConfigError
from escalate.config import env_file_problems, get_settings
from escalate.db.models import Base
from escalate.db.session import get_engine
from escalate.evidence.store import EvidenceKeyMissing
from escalate.export.pdf import PdfUnavailable
from escalate.llm.client import LLMNotConfigured
from escalate.netguard import UnsafeEndpoint
from escalate.pii import install_log_filter
from escalate.playbooks.loader import PlaybookError
from escalate.safety import HarassmentPattern, NoEvidence, RateLimited
from escalate.scheduler import jobs

ROOT = Path(__file__).resolve().parents[2]


def init_db() -> None:
    """Run Alembic migrations when available, else create tables directly."""
    ini = ROOT / "alembic.ini"
    if ini.is_file():
        from alembic import command
        from alembic.config import Config

        cfg = Config(str(ini))
        cfg.attributes["configure_logger"] = False  # keep uvicorn's logging (see migrations/env.py)
        cfg.set_main_option("script_location", str(ROOT / "migrations"))
        cfg.set_main_option("sqlalchemy.url", get_settings().database_url)
        command.upgrade(cfg, "head")
    else:
        Base.metadata.create_all(get_engine())


def _start_scheduler() -> Any:
    sched = jobs.make_scheduler()
    jobs.add_daily_deadline_scan(sched)
    if get_settings().demo_mode:
        jobs.add_demo_cleanup(sched)
    sched.start()
    runner.set_scheduler(sched)
    return sched


log = logging.getLogger("uvicorn.error")  # shown with uvicorn's own startup lines


def startup_warnings() -> list[str]:
    """Config problems to show in the console at startup (they would otherwise surface later as
    500s). Startup never contacts the network or the LLM."""
    warnings = env_file_problems()
    s = get_settings()
    if not s.fernet_key:
        warnings.append("FERNET_KEY is empty: evidence uploads and demo data will fail until set")
    if s.allow_lan:
        warnings.append(
            "ALLOW_LAN=true: the API is reachable from your network and has NO login. Anyone on "
            "the network can read your cases and send letters. Turn it off when you are done."
        )
    return warnings


def create_app(startup: bool = True) -> FastAPI:
    install_log_filter()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        sched = None
        if startup:
            for w in startup_warnings():
                log.warning(w)
            init_db()
            runner.configure()
            sched = _start_scheduler()
        yield
        if sched is not None:
            runner.set_scheduler(None)
            sched.shutdown(wait=False)

    # Swagger UI / ReDoc pages load scripts from a CDN: development only (API_DOCS=true, which
    # `make api` sets). The OpenAPI JSON itself is always available.
    docs = get_settings().api_docs
    app = FastAPI(
        title="Escalate",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
    )
    # Middleware runs outermost-last: Host check, then CORS (answers preflights), then CSRF,
    # then the optional app lock, then rate and body-size limits.
    settings = get_settings()
    app.state.lock = AppLock()
    app.add_middleware(RequestLimits)
    app.add_middleware(AppLockGuard, lock=app.state.lock)
    app.add_middleware(CsrfGuard)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=split_list(settings.web_origin),  # the web app calls the API from the browser
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", CSRF_HEADER],
        allow_credentials=True,  # the app lock's session cookie (explicit origins only)
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=split_list(settings.allowed_hosts))
    app.add_middleware(SecurityHeaders)  # outermost: also on refusals from the guards above
    app.include_router(auth.router)
    app.include_router(cases.router)
    app.include_router(messages.router)
    app.include_router(system.router)

    errors: list[tuple[type[Exception], int, Callable[[Exception], dict[str, Any]] | None]] = [
        (UnsupportedFacts, 422, lambda e: {"issues": e.issues}),  # type: ignore[attr-defined]
        (RateLimited, 429, None),
        (NoEvidence, 422, None),
        (HarassmentPattern, 403, None),
        (runner.RunnerError, 409, None),
        (RecipientNotConfirmed, 409, lambda e: {"recipient": e.recipient}),  # type: ignore[attr-defined]
        (ApprovalError, 409, None),
        (NotApproved, 409, None),
        (ProofRequired, 422, None),
        (EmailConfigError, 400, None),
        (EvidenceKeyMissing, 500, None),
        (PlaybookError, 500, None),
        (PdfUnavailable, 503, None),
        (NotImplementedError, 501, None),
        (LLMNotConfigured, 503, None),
        (UnsafeEndpoint, 400, None),
        (openai.APIConnectionError, 503, lambda e: {"hint": "is the LLM server running?"}),
    ]
    for exc_type, code, extra in errors:

        def handler(
            _req: Request, exc: Exception, code: int = code, extra: Any = extra
        ) -> JSONResponse:
            body: dict[str, Any] = {"detail": str(exc)}
            if extra:
                # dict.update on a JSON body (bandit B610 is about Django's QuerySet.extra).
                body.update(extra(exc))  # nosec B610
            return JSONResponse(body, status_code=code)

        app.add_exception_handler(exc_type, handler)
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(Exception, internal_error)
    return app


def validation_error(_req: Request, exc: Exception) -> JSONResponse:
    """422 without echoing the submitted values back (they may be a password or API key)."""
    errors = exc.errors() if isinstance(exc, RequestValidationError) else []
    detail = [
        {"loc": list(e.get("loc", ())), "msg": e.get("msg", ""), "type": e.get("type", "")}
        for e in errors
    ]
    return JSONResponse({"detail": detail}, status_code=422)


def internal_error(_req: Request, exc: Exception) -> JSONResponse:
    """An unexpected error: the client gets an id to quote, the console gets the traceback
    (masked by the PII log filter). Never a stack trace or internal message in the response."""
    error_id = uuid.uuid4().hex[:12]
    log.error("unhandled error %s: %s", error_id, type(exc).__name__, exc_info=exc)
    return JSONResponse(
        {"detail": f"internal error (id {error_id}); see the API console", "error_id": error_id},
        status_code=500,
    )


app = create_app()
