"""HTTP server: Starlette app factory + uvicorn entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Mount, Route

from maasmcp.auth import require_bearer
from maasmcp.config import MaasmcpConfig
from maasmcp.maas.client import MaasClient
from maasmcp.maas.errors import MAASError
from maasmcp.maas.singleton import get_shared_client, set_shared_client
from maasmcp.observability import configure_logging
from maasmcp.registry import mcp
from maasmcp.request_log import request_log_middleware

# A lifespan context: takes the ASGI app, returns an async context manager
# that drives startup/shutdown. Matches Starlette's lifespan contract and
# the ``mcp_app.router.lifespan_context`` we wrap.
Lifespan = Callable[[Starlette], AbstractAsyncContextManager[Any]]


def _build_lifespan(cfg: MaasmcpConfig, inner_lifespan: Lifespan) -> Lifespan:
    """Return an async context manager that drives both lifecycles.

    The MCP SDK's lifespan starts the ``StreamableHTTPSessionManager``
    task group. Ours additionally constructs a shared
    :class:`MaasClient` and installs it on :mod:`maasmcp.maas.singleton`
    so tool wrappers can fetch it at call time. Order matters: we enter
    the inner lifespan first (so the session manager exists), then build
    the client, and only yield once both are live.
    """

    @asynccontextmanager
    async def _lifespan(_app: Starlette) -> AsyncIterator[None]:
        async with inner_lifespan(_app):
            # Pass the full config so server.max_paginated_items reaches the
            # client (a bare MaasConfig would silently fall back to 1000).
            client = MaasClient(
                cfg,
                timeout_seconds=cfg.server.request_timeout_seconds,
            )
            await client.__aenter__()
            set_shared_client(client)
            try:
                yield
            finally:
                set_shared_client(None)
                await client.__aexit__(None, None, None)

    return _lifespan


# Readiness probes must answer fast: a wedged MAAS must not tie up a handler
# for the full request_timeout_seconds (default 300s) while the orchestrator's
# probe timeout (typically 1-10s) has long expired.
_READYZ_UPSTREAM_TIMEOUT_S = 10.0


async def _readyz(_req: Request) -> PlainTextResponse:
    """Readiness probe — verifies MAAS upstream is reachable.

    Distinction from /healthz:
    - ``/healthz`` is a process-liveness probe (no upstream dependency);
      k8s should never restart the pod based on this alone.
    - ``/readyz`` (this) is a readiness probe — k8s should only route
      traffic to this pod when MAAS is reachable. Returns 200 on
      success, 503 on any upstream failure (timeout, connect error, 5xx).
      Uses a dedicated short timeout, not the tool-call budget.
    """
    try:
        client = get_shared_client()
        await client.get("/api/2.0/version/", timeout=_READYZ_UPSTREAM_TIMEOUT_S)
    except (MAASError, httpx.HTTPError, RuntimeError) as exc:
        # MAASError: what MaasClient actually raises on upstream failure
        # (timeout, connect error, 4xx/5xx). httpx.HTTPError is kept for
        # any call path that escapes the client's translation layer.
        return PlainTextResponse(
            f"not ready: {type(exc).__name__}",
            status_code=503,
        )
    return PlainTextResponse("ready", status_code=200)


def create_app(cfg: MaasmcpConfig) -> Starlette:
    """Build the Starlette ASGI app: logging, auth, /healthz, /mcp mount.

    The MCP SDK's :meth:`MCPServer.streamable_http_app` returns a Starlette that
    routes at ``/mcp`` internally; ``json_response=True`` selects plain JSON
    replies over SSE. We mount it at ``/`` so the public URL is
    exactly ``/mcp`` (matching the README's documented contract). The MCP app
    owns its own ``lifespan_context`` (which starts the
    :class:`StreamableHTTPSessionManager` task group); we wrap it so the
    shared :class:`MaasClient` is also constructed in startup and torn down
    in shutdown, then forward the wrapped lifespan to the outer Starlette so
    ``asgi-lifespan`` drives both together.
    """
    configure_logging(cfg.server.log_level)
    mcp_app = mcp.streamable_http_app(json_response=True)
    # Per-request logging is registered FIRST so it observes every request,
    # including 401 responses from the bearer middleware.
    return Starlette(
        routes=[
            Route("/healthz", lambda req: PlainTextResponse("healthy")),
            Route("/readyz", _readyz),
            Mount("/", app=mcp_app),
        ],
        middleware=[request_log_middleware(), require_bearer(cfg.server.bearer_token)],
        lifespan=_build_lifespan(cfg, mcp_app.router.lifespan_context),
    )


def run(cfg: MaasmcpConfig) -> None:
    """Blocking uvicorn entry point used by the CLI."""
    uvicorn.run(
        create_app(cfg),
        host=cfg.server.host,
        port=cfg.server.port,
        log_level=cfg.server.log_level,
    )
