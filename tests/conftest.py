from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from escalate.db import session as db_session
from escalate.db.models import Base


@pytest.fixture
def db() -> Iterator[Session]:
    """A fresh in-memory SQLite database, bound as the global engine."""
    engine = db_session.configure("sqlite://")
    Base.metadata.create_all(engine)
    s = db_session.session_factory()()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()
