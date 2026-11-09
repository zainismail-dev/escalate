"""Hosted mode: one upload (read, OCR, encrypt, store) per user at a time; a second one while the
first is running is a 409 "upload in progress". In memory: the beta runs one API process."""

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException

_busy: set[str] = set()
_guard = threading.Lock()


@contextmanager
def one_at_a_time(user_id: str | None) -> Iterator[None]:
    if user_id is None:  # local mode: one user, no limit
        yield
        return
    with _guard:
        if user_id in _busy:
            raise HTTPException(409, "upload in progress: wait for it to finish")
        _busy.add(user_id)
    try:
        yield
    finally:
        with _guard:
            _busy.discard(user_id)
