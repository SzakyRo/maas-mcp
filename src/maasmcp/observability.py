"""structlog configuration, logging helpers, and request/MAAS-call sanitizers."""

from __future__ import annotations

import logging
import re
import sys

import structlog


class _AsgiDisconnectFilter(logging.Filter):
    """Demote uvicorn's "ASGI callable returned without completing response".

    With MCP streamable-HTTP this fires once per abandoned SSE stream —
    i.e. on every client disconnect — while the request actually returned
    200. Not worth an ERROR; pass it through at DEBUG instead.
    """

    _MESSAGE = "ASGI callable returned without completing response"

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.ERROR and self._MESSAGE in record.getMessage():
            record.levelno = logging.DEBUG
            record.levelname = "DEBUG"
        return True


def configure_logging(level: str = "info") -> None:
    """Configure structlog JSON output to stderr.

    stderr is chosen deliberately: stdout is protocol-safe only because this
    server has no stdio transport. If one is ever added, stdout logging would
    corrupt MCP framing — stderr stays safe for both transports.

    One-shot semantics: ``logging.basicConfig`` is a no-op when handlers
    already exist, so a second call (tests, uvicorn reload) silently keeps
    the first level. Call once at startup.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(stream=sys.stderr, level=log_level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        cache_logger_on_first_use=True,
    )
    # MCP streamable-HTTP clients hold a long-lived SSE GET on /mcp for
    # server-initiated messages and abandon it freely on reconnect (clients
    # churn sessions every few seconds in practice). Each abandoned stream
    # makes uvicorn log "ASGI callable returned without completing response"
    # at ERROR next to a 200 — pure noise for this transport. Downgrade to
    # DEBUG so alerts built on ERROR aren't drowned in disconnect chatter.
    logging.getLogger("uvicorn.error").addFilter(_AsgiDisconnectFilter())


def bearer_prefix(token: str) -> str:
    """Return a safe log-correlation prefix from a bearer token.

    Never log the full token. Returns at most 6 chars — but only when the
    token is long enough that 6 chars is a *prefix* (≥ 8 chars). Short
    tokens are reported as '<short>' so a weak token is never printed in
    full.
    """
    if not token:
        return "anon"
    if len(token) < 8:
        return "<short>"
    return token[:6]


# Segments that look like MAAS ids (6-char lowercase alnum host keys) or
# plain integers are collapsed to {id} for logging so request logs don't
# mirror every individual machine/partition the fleet touches.
_IDISH_SEGMENT_RE = re.compile(r"^(\d+|[a-z0-9]{6})$")


def sanitize_path(path: str) -> str:
    """Collapse id-like path segments to ``{id}`` for safe, low-noise logs.

    Static segments (api, mcp, healthz, …) pass through, as do empty
    segments (leading/trailing slashes); integer ids and MAAS-style 6-char
    system ids become ``{id}``.
    """
    parts = []
    for p in path.split("/"):
        if p and _IDISH_SEGMENT_RE.match(p):
            parts.append("{id}")
        else:
            parts.append(p)
    return "/".join(parts)
