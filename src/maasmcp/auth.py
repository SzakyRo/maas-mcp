"""Bearer-token ASGI auth middleware."""

from __future__ import annotations

import hmac

from starlette.middleware import Middleware
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

EXEMPT_PATHS = frozenset({"/healthz"})


def require_bearer(expected_token: str) -> Middleware:
    """Return a Starlette middleware that requires a matching bearer token.

    Exempt paths: /healthz. Comparison uses hmac.compare_digest. Failures
    return a bare 401 with no body (so we don't leak why auth failed).
    """
    return Middleware(_BearerAuth, expected_token=expected_token)


class _BearerAuth:
    def __init__(self, app: ASGIApp, *, expected_token: str) -> None:
        self.app = app
        self.expected_token = expected_token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return

        if scope["type"] == "websocket":
            # Fail closed: no websocket routes exist today, and any future one
            # must not slip past bearer auth by falling through this check.
            await send({"type": "websocket.close", "code": 4403, "reason": "unsupported"})
            return

        if scope["type"] != "http":
            # Fail closed rather than guess at an unauthenticated passthrough
            # for a scope type we don't understand.
            raise RuntimeError(f"unsupported scope type for bearer auth: {scope['type']!r}")

        path = scope.get("path", "")
        if path in EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        # Collect ALL Authorization headers: RFC 7235 allows only one set of
        # credentials per request. dict() would silently keep the last one,
        # letting a confused client (or a sloppy proxy chain) smuggle a
        # mismatched pair past intent checks — reject instead.
        auth_values = [
            v
            for k, v in scope.get("headers", [])
            if k.lower() == b"authorization"
        ]
        if len(auth_values) != 1:
            response = Response(status_code=401)
            await response(scope, receive, send)
            return
        auth = auth_values[0].decode("ascii", errors="replace")
        presented = ""
        if auth.startswith("Bearer "):
            presented = auth[len("Bearer ") :]

        # Never accept an empty presented token — if the server were ever
        # misconfigured with an empty expected token, compare_digest("", "")
        # would silently authenticate headerless requests.
        if not presented or not self.expected_token:
            response = Response(status_code=401)
            await response(scope, receive, send)
            return

        # hmac.compare_digest raises TypeError on non-ASCII str; a client
        # sending one must get a clean bare 401, not an unhandled 500.
        if not presented.isascii() or not self.expected_token.isascii():
            response = Response(status_code=401)
            await response(scope, receive, send)
            return

        if hmac.compare_digest(presented, self.expected_token):
            await self.app(scope, receive, send)
            return

        response = Response(status_code=401)
        await response(scope, receive, send)
