"""Per-request ASGI logging middleware.

Emits a single structlog ``info`` event per HTTP request with:
``client_ip``, ``bearer_prefix``, ``method``, ``tool``, ``latency_ms``,
``path``, and ``outcome`` (status code or ``"exception"``).

Body buffering: up to 4 MiB of the request body is buffered so the
middleware can extract the JSON-RPC method and tool name (bounded at 1 MiB
for parsing); anything larger streams past the buffer without being fully
held in memory. Buffered chunks are replayed to the inner app via a
buffering ``receive`` wrapper.
"""

from __future__ import annotations

import json
import time
from collections import deque
from collections.abc import MutableMapping
from typing import Any, cast

import structlog
from starlette.middleware import Middleware
from starlette.types import ASGIApp, Receive, Scope, Send

from maasmcp.observability import bearer_prefix, sanitize_path

log = structlog.get_logger(__name__)

_MAX_BODY_BYTES = 1 << 20  # 1 MiB body cap for tool-name extraction
# Bound on bytes held in the replay deque before the app starts. Past this,
# remaining chunks stream straight from the original receive — an oversized
# (possibly unauthenticated) POST cannot make us buffer its full body.
# Coincidentally identical to MCP SDK v2's streamable-HTTP request-body
# limit (DEFAULT_MAX_REQUEST_BODY_SIZE = 4 MiB): bodies past it stream
# through here and are then rejected downstream with HTTP 413.
_MAX_BUFFERED_BYTES = 4 << 20  # 4 MiB


def _client_ip(scope: Scope) -> str:
    client = scope.get("client")
    if client and isinstance(client, tuple) and client:
        return str(client[0])
    return "-"


def _extract_bearer(scope: Scope) -> str:
    """Return the request bearer's safe log prefix.

    The full token is derived and discarded inside this function — via
    :func:`observability.bearer_prefix`, which returns at most 6 chars of a
    long token and '<short>' for a short one — never propagated into other
    Python call frames where it could be accidentally logged or persisted.

    Duplicate Authorization headers: auth's middleware rejects such requests
    with 401 before this runs; taking the FIRST value here (not dict()'s
    silent last-one-wins) keeps the logged prefix consistent with the
    credential that was evaluated on the session that did get through.
    """
    headers_list = scope.get("headers") or []
    auth_values = [
        v for k, v in cast(list[tuple[bytes, bytes]], headers_list) if k.lower() == b"authorization"
    ]
    raw = auth_values[0].decode("ascii", errors="replace") if auth_values else ""
    if raw.startswith("Bearer "):
        return bearer_prefix(raw[len("Bearer ") :])
    return "anon"


async def _drain_body(receive: Receive) -> tuple[deque[dict[str, Any]], bytes, bool, bool]:
    """Read ``http.request`` chunks into a bounded deque.

    Returns ``(buffered_chunks, captured_body_bytes, body_was_complete, overflow)``.

    Up to ``_MAX_BUFFERED_BYTES`` of chunk data is buffered for replay; the
    first ``_MAX_BODY_BYTES`` of that is additionally captured for tool-name
    extraction. If the body exceeds the buffering bound, we stop consuming
    (``overflow=True``) and the replaying receive produced by
    :func:`_make_replaying_receive` streams the remainder from the original
    channel, so memory stays bounded even for unauthenticated jumbo POSTs.
    """
    out: deque[dict[str, Any]] = deque()
    captured = bytearray()
    buffered_bytes = 0
    while True:
        msg = cast(dict[str, Any], await receive())
        mtype = msg.get("type")
        if mtype == "http.request":
            body = msg.get("body", b"") or b""
            more = bool(msg.get("more_body", False))
            remaining_parse = _MAX_BODY_BYTES - len(captured)
            if remaining_parse > 0:
                captured.extend(body[:remaining_parse])
            out.append(msg)
            buffered_bytes += len(body)
            if not more:
                return out, bytes(captured), True, False
            if buffered_bytes >= _MAX_BUFFERED_BYTES:
                return out, bytes(captured), False, True
        else:
            # http.disconnect or lifespan — return immediately.
            out.append(msg)
            return out, bytes(captured), False, False


def _make_replaying_receive(
    buffered: deque[dict[str, Any]], original: Receive, *, overflow: bool
) -> Receive:
    """Build a Receive that replays buffered chunks, then streams or disconnects."""

    async def replaying() -> dict[str, Any]:
        if buffered:
            return buffered.popleft()
        if overflow:
            # Body was bigger than the replay buffer — the unconsumed tail is
            # still on the original channel.
            return cast(dict[str, Any], await original())
        return {"type": "http.disconnect"}

    return replaying


def _parse_tool(body: bytes) -> tuple[str | None, str | None]:
    """Best-effort extraction of (jsonrpc method, tool name) from body bytes.

    JSON-RPC batch requests arrive as a list of envelopes; log the first
    member's method/tool rather than nothing at all. Bodies past the 1 MiB
    parse cap (see ``_drain_body``) are truncated JSON that fails to parse —
    those legitimately yield ``(None, None)``.
    """
    if not body:
        return None, None
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None, None
    if isinstance(payload, list):
        if not payload or not isinstance(payload[0], dict):
            return None, None
        payload = payload[0]
    if not isinstance(payload, dict):
        return None, None
    raw_method = payload.get("method")
    method_s: str | None = str(raw_method) if raw_method is not None else None
    tool: str | None = None
    params = payload.get("params")
    if isinstance(params, dict):
        name = params.get("name")
        if isinstance(name, str):
            tool = name
    return method_s, tool


def request_log_middleware() -> Middleware:
    """Return a Starlette middleware that logs one structured event per request."""
    return Middleware(_RequestLogger)


class _RequestLogger:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.monotonic()
        path = sanitize_path(scope.get("path", ""))
        client_ip = _client_ip(scope)
        bp = _extract_bearer(scope)
        http_method = scope.get("method", "")

        # Drain INSIDE the try: if the client disconnects mid-body, the drain
        # raises and we would otherwise skip the log entirely — abandoned
        # uploads are exactly the pattern worth having a trace of (churning
        # MCP clients per the observability comments).
        body = b""
        body_complete = False
        outcome_holder: dict[str, str] = {"value": "unknown"}

        async def wrapped_send(message: MutableMapping[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                status = int(message.get("status", 0))
                outcome_holder["value"] = str(status)
            await send(dict(message))

        try:
            buffered, body, body_complete, overflow = await _drain_body(receive)
            replaying_receive = _make_replaying_receive(buffered, receive, overflow=overflow)
            await self.app(scope, replaying_receive, wrapped_send)
        except Exception:
            outcome_holder["value"] = "exception"
            raise
        finally:
            latency_ms = (time.monotonic() - start) * 1000.0
            jsonrpc_method, tool = _parse_tool(body)
            log.info(
                "http_request",
                client_ip=client_ip,
                bearer_prefix=bp,
                method=str(jsonrpc_method or http_method),
                tool=tool or "",
                path=path,
                latency_ms=round(latency_ms, 2),
                outcome=outcome_holder["value"],
            )
            _ = body_complete  # reserved for future use


__all__ = ["request_log_middleware"]
