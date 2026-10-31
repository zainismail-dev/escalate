"""Run Alembic against a URL (hosted settings come from the environment)."""

from pathlib import Path

from alembic import command
from alembic.config import Config

REPO = Path(__file__).resolve().parents[2]


def config(url: str) -> Config:
    cfg = Config(str(REPO / "alembic.ini"))
    cfg.attributes["configure_logger"] = False
    cfg.set_main_option("script_location", str(REPO / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def upgrade(url: str, rev: str = "head") -> None:
    command.upgrade(config(url), rev)


def downgrade(url: str, rev: str = "base") -> None:
    command.downgrade(config(url), rev)
