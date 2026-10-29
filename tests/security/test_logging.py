"""PII never reaches the console: uvicorn's own loggers, tracebacks, and request handling."""

import logging

import pytest

from escalate.pii import LOGGERS, PiiFilter, install_log_filter

CARD = "4111 1111 1111 1111"


def test_uvicorn_loggers_and_their_handlers_are_filtered() -> None:
    handler = logging.StreamHandler()
    access = logging.getLogger("uvicorn.access")
    access.addHandler(handler)
    try:
        install_log_filter()
        for name in LOGGERS:
            assert any(isinstance(f, PiiFilter) for f in logging.getLogger(name).filters), name
        assert any(isinstance(f, PiiFilter) for f in handler.filters)
    finally:
        access.removeHandler(handler)


def test_access_log_query_strings_are_masked(caplog: pytest.LogCaptureFixture) -> None:
    install_log_filter()
    log = logging.getLogger("uvicorn.access")
    with caplog.at_level(logging.INFO, logger="uvicorn.access"):
        log.info('%s - "%s %s HTTP/1.1" %d', "127.0.0.1", "GET", f"/cases?q={CARD}", 200)
    assert CARD not in caplog.text
    assert "1111" in caplog.text  # last four kept


def test_tracebacks_are_masked() -> None:
    record = logging.LogRecord("uvicorn.error", logging.ERROR, __file__, 1, "boom", None, None)
    try:
        raise ValueError(f"bad card {CARD}, otp: 493021")
    except ValueError:
        import sys

        record.exc_info = sys.exc_info()
    PiiFilter().filter(record)
    out = logging.Formatter().format(record)
    assert CARD not in out and "493021" not in out
    assert "ValueError" in out


def test_request_bodies_are_never_logged() -> None:
    """No middleware or handler logs bodies: nothing in the API package reads them for logs."""
    from pathlib import Path

    import escalate.api as api

    src = "\n".join(p.read_text() for p in Path(api.__file__).parent.rglob("*.py"))
    for needle in ("request.body()", "await request.json()", "log.info(body", "log.debug(body"):
        assert needle not in src


def test_uvicorn_access_log_still_formats_and_is_masked() -> None:
    """Second review N5: the filter set record.args=None, which broke uvicorn's access log
    formatter (it unpacks the args): every request logged a formatting error instead."""
    from uvicorn.logging import AccessFormatter

    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:5000", "GET", f"/cases?q={CARD}", "1.1", 200),
        None,
    )
    assert PiiFilter().filter(record)
    out = AccessFormatter(
        '%(client_addr)s - "%(request_line)s" %(status_code)s', use_colors=False
    ).format(record)
    assert out == '127.0.0.1:5000 - "GET /cases?q=•••• 1111 HTTP/1.1" 200 OK'
    assert CARD not in out


def test_dict_args_are_masked() -> None:
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "card %(c)s", None, None)
    record.args = {"c": CARD}
    PiiFilter().filter(record)
    assert CARD not in record.getMessage() and "1111" in record.getMessage()
