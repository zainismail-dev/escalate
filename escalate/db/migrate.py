"""Run the Alembic migrations (the API does this at startup; `make migrate-hosted` too)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def upgrade(url: str) -> bool:
    """Upgrade `url` to the latest revision. False when alembic.ini isn't shipped."""
    ini = ROOT / "alembic.ini"
    if not ini.is_file():
        return False
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(ini))
    cfg.attributes["configure_logger"] = False  # keep uvicorn's logging (see migrations/env.py)
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    return True
