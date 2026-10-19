"""Tests for logging configuration and sanitizers."""

from __future__ import annotations

import logging

from maasmcp.observability import _AsgiDisconnectFilter, configure_logging


def test_asgi_disconnect_filter_demotes_error_to_debug() -> None:
    record = logging.LogRecord(
        name="uvicorn.error",
        level=logging.ERROR,
        pathname="",
        lineno=0,
        msg="ASGI callable returned without completing response.",
        args=(),
        exc_info=None,
    )
    assert _AsgiDisconnectFilter().filter(record) is True
    assert record.levelno == logging.DEBUG


def test_asgi_disconnect_filter_leaves_other_errors_alone() -> None:
    record = logging.LogRecord(
        name="uvicorn.error",
        level=logging.ERROR,
        pathname="",
        lineno=0,
        msg="some other server error",
        args=(),
        exc_info=None,
    )
    assert _AsgiDisconnectFilter().filter(record) is True
    assert record.levelno == logging.ERROR


def test_configure_logging_attaches_filter_to_uvicorn_error() -> None:
    configure_logging("info")
    logger = logging.getLogger("uvicorn.error")
    assert any(isinstance(f, _AsgiDisconnectFilter) for f in logger.filters)
