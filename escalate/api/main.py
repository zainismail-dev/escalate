"""FastAPI app. The scheduler runs inside this process and starts with the app.

uv run uvicorn escalate.api.main:app --reload
"""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import openai
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from escalate import __version__
from escalate.agent import runner
from escalate.agent.approval import ApprovalError, UnsupportedFacts
from escalate.api.routes import cases, messages, system
from escalate.channels import NotApproved, ProofRequired
from escalate.channels.email_smtp import EmailConfigError
from escalate.config import env_file_problems, get_settings
from escalate.db.models import Base
from escalate.db.session import get_engine
from escalate.evidence.store import EvidenceKeyMissing
from escalate.export.pdf import PdfUnavailable
from escalate.llm.client import LLMNotConfigured
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
    if not get_settings().fernet_key:
        warnings.append("FERNET_KEY is empty: evidence uploads and demo data will fail until set")
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

    app = FastAPI(title="Escalate", version=__version__, lifespan=lifespan)
    # The web app (web/) calls the API from the browser; only its origin is allowed.
    origins = [o.strip() for o in get_settings().web_origin.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )
    app.include_router(cases.router)
    app.include_router(messages.router)
    app.include_router(system.router)

    errors: list[tuple[type[Exception], int, Callable[[Exception], dict[str, Any]] | None]] = [
        (UnsupportedFacts, 422, lambda e: {"issues": e.issues}),  # type: ignore[attr-defined]
        (RateLimited, 429, None),
        (NoEvidence, 422, None),
        (HarassmentPattern, 403, None),
        (runner.RunnerError, 409, None),
        (ApprovalError, 409, None),
        (NotApproved, 409, None),
        (ProofRequired, 422, None),
        (EmailConfigError, 400, None),
        (EvidenceKeyMissing, 500, None),
        (PlaybookError, 500, None),
        (PdfUnavailable, 503, None),
        (NotImplementedError, 501, None),
        (LLMNotConfigured, 503, None),
        (openai.APIConnectionError, 503, lambda e: {"hint": "is the LLM server running?"}),
    ]
    for exc_type, code, extra in errors:

        def handler(
            _req: Request, exc: Exception, code: int = code, extra: Any = extra
        ) -> JSONResponse:
            body: dict[str, Any] = {"detail": str(exc)}
            if extra:
                body.update(extra(exc))
            return JSONResponse(body, status_code=code)

        app.add_exception_handler(exc_type, handler)
    return app


app = create_app()
