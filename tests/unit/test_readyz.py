"""Tests for the /readyz MAAS-readiness probe."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

import maasmcp.server as server_mod
from maasmcp.maas.errors import MCPUpstreamError, MCPUpstreamTimeout
from maasmcp.maas.singleton import set_shared_client


class _StubClient:
    """Drop-in replacement for MaasClient with a controllable .get() coroutine."""

    def __init__(self, response: Any | BaseException) -> None:
        self._response = response
        self.last_timeout: float | None = None

    async def get(
        self, path: str, params: Any = None, *, timeout: float | None = None
    ) -> Any:
        self.last_timeout = timeout
        if isinstance(self._response, BaseException):
            raise self._response
        return self._response


@pytest.mark.asyncio
async def test_readyz_returns_200_when_maas_reachable() -> None:
    """200 + 'ready' when the shared client can reach MAAS /version/.

    Also pins the probe timeout: /readyz must not spend the full tool-call
    budget (default 300s) on a wedged MAAS — orchestrator probes expire long
    before that.
    """
    stub = _StubClient({"version": "3.7.2"})
    set_shared_client(stub)  # type: ignore[arg-type]
    try:
        resp = await server_mod._readyz(None)  # type: ignore[arg-type]
    finally:
        set_shared_client(None)
    assert resp.status_code == 200
    assert b"ready" in resp.body
    assert stub.last_timeout == server_mod._READYZ_UPSTREAM_TIMEOUT_S


@pytest.mark.asyncio
async def test_readyz_returns_503_on_httpx_timeout() -> None:
    """503 + error class name when MAAS doesn't respond in time."""
    set_shared_client(_StubClient(httpx.ConnectError("connection refused")))
    try:
        resp = await server_mod._readyz(None)  # type: ignore[arg-type]
    finally:
        set_shared_client(None)
    assert resp.status_code == 503
    assert b"not ready" in resp.body
    assert b"ConnectError" in resp.body


@pytest.mark.asyncio
async def test_readyz_returns_503_on_5xx_upstream() -> None:
    """503 when MAAS /version/ returns 5xx (treated as upstream HTTP error)."""
    set_shared_client(
        _StubClient(
            httpx.HTTPStatusError(
                "server error",
                request=httpx.Request("GET", "https://maas.example.com/MAAS/api/2.0/version/"),
                response=httpx.Response(503, text="unavailable"),
            )
        )
    )
    try:
        resp = await server_mod._readyz(None)  # type: ignore[arg-type]
    finally:
        set_shared_client(None)
    assert resp.status_code == 503
    assert b"HTTPStatusError" in resp.body


@pytest.mark.asyncio
async def test_readyz_returns_503_when_no_client_installed() -> None:
    """503 when the server hasn't installed the shared client yet.

    Startup-race case: probe hits before lifespan startup ran
    (e.g. unit test calling _readyz directly). Returning 503 is correct —
    the pod isn't ready to serve traffic.
    """
    set_shared_client(None)
    resp = await server_mod._readyz(None)  # type: ignore[arg-type]
    assert resp.status_code == 503
    assert b"not ready" in resp.body


@pytest.mark.asyncio
async def test_readyz_returns_503_on_upstream_error_types() -> None:
    """Regression: MaasClient translates every upstream failure into
    MCPUpstreamError/MCPUpstreamTimeout (plain Exception subclasses), which
    escaped the old ``except (httpx.HTTPError, RuntimeError)`` and surfaced
    as a Starlette 500 instead of the documented 503."""
    for exc in (
        MCPUpstreamError("upstream 503", status_code=503, url="https://maas.example.com"),
        MCPUpstreamTimeout("upstream timed out after retries", url="/api/2.0/version/"),
    ):
        set_shared_client(_StubClient(exc))
        try:
            resp = await server_mod._readyz(None)  # type: ignore[arg-type]
        finally:
            set_shared_client(None)
        assert resp.status_code == 503, f"{type(exc).__name__} escaped as non-503"
        assert b"not ready" in resp.body


def test_healthz_remains_liveness_only() -> None:
    """Regression guard: /healthz must NOT depend on MAAS reachability.

    The fix deliberately split readiness (/readyz) from liveness (/healthz).
    If a future change accidentally moves the MAAS probe into /healthz,
    k8s would restart the pod during transient MAAS outages — a bug.
    """
    import inspect

    src = inspect.getsource(server_mod)
    # /healthz must be a one-liner with no shared-client lookup.
    healthz_block = src.split('Route("/healthz"', 1)[1].split(")", 1)[0]
    assert "get_shared_client" not in healthz_block, (
        "/healthz must remain a process-liveness probe — use /readyz for MAAS reachability instead"
    )
