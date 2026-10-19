"""Integration tests for the streamable-HTTP transport.

Drives the real ASGI app under uvicorn on a random port so that:

  * the MCP SDK's :class:`StreamableHTTPSessionManager` actually starts
    (TestClient alone doesn't drive its task group — the inner lifespan
    must run, or every request 500s with "Task group is not initialized"),
  * requests traverse the real HTTP stack — bearer auth, request logging,
    Starlette routing, and the streamable-HTTP ASGI subapp in turn.

The wire-protocol semantics (initialize → list_tools, MCP envelope
shapes, tool registration) are covered by the in-memory transport test
that drives ``mcp.Client`` directly against the server. This file proves
the production HTTP transport wires up correctly over real sockets.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx
import uvicorn
from mcp import Client

from maasmcp.config import MaasmcpConfig
from maasmcp.server import create_app

_MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


def _init_payload(id_: int = 1) -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            # Broadly compatible version the server can negotiate with;
            # v2's transport accepts self-describing POSTs without a
            # handshake, but initialize is still required to get a
            # server-generated mcp-session-id (asserted below).
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "maasmcp-test", "version": "0.0.0"},
        },
        "id": id_,
    }


@pytest.fixture
async def running_server(monkeypatch):
    """Start the production ASGI app under uvicorn on a random port."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "test-token-0123456789")
    cfg = MaasmcpConfig.load(None)
    app = create_app(cfg)

    # Bind port 0 (kernel-assigned) and read back the actual port after
    # startup — no bind-then-release race window between probe and serve.
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", access_log=False)
    server = uvicorn.Server(config)
    serve_task = asyncio.create_task(server.serve())
    try:
        # Wait for startup (server.started flips True once the lifespan
        # startup has completed and the StreamableHTTPSessionManager task
        # group is initialized).
        for _ in range(200):  # up to ~10s
            if server.started:
                break
            await asyncio.sleep(0.05)
        else:
            raise RuntimeError("uvicorn did not start within 10s")
        port = server.servers[0].sockets[0].getsockname()[1]
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(serve_task, timeout=5)
        except TimeoutError:
            serve_task.cancel()


async def _post_mcp_headers(client: httpx.AsyncClient, *, authed: bool) -> httpx.Response:
    """POST an initialize request and return once headers are received.

    With ``json_response=True`` the MCP streamable-HTTP transport replies
    synchronously as ``application/json`` (no streaming, no SSE). The
    MCP client closes the connection naturally on receipt, which is what
    keeps the handshake healthy under the SDK 1.28.x transport.
    """
    headers = _MCP_HEADERS if not authed else {"Authorization": "Bearer test-token-0123456789", **_MCP_HEADERS}
    req = client.build_request("POST", "/mcp", json=_init_payload(), headers=headers)
    return await client.send(req, stream=True)


@pytest.mark.asyncio
async def test_streamable_http_transport_full_round_trip(running_server: str) -> None:
    """End-to-end: the production app serves the streamable-HTTP endpoint.

    Covers, in one pass:
      * ``/healthz`` is exempt from bearer auth (200).
      * ``/mcp`` without a bearer returns 401 (no body that leaks why).
      * ``/mcp`` with a bearer reaches the running MCP session manager
        and the server returns ``200 text/event-stream`` with an
        ``mcp-session-id`` header — proof that the inner lifespan started
        and the MCP SDK created a session for this connection.
    """
    async with httpx.AsyncClient(base_url=running_server) as client:
        # /healthz is exempt from auth.
        assert (await client.get("/healthz")).status_code == 200

        # /mcp without bearer → 401. (Empty-body contract is asserted by
        # tests/unit/test_auth.py; here we only need the status to prove
        # the bearer middleware is wired into the production HTTP stack.)
        no_auth = await _post_mcp_headers(client, authed=False)
        try:
            assert no_auth.status_code == 401
        finally:
            await no_auth.aclose()

        # /mcp with bearer reaches the live StreamableHTTPSessionManager.
        # Without the lifespan fix this 500s with "Task group is not
        # initialized"; without the Mount("/") fix it 307s/404s.
        authed = await _post_mcp_headers(client, authed=True)
        try:
            assert authed.status_code == 200, (authed.status_code, authed.text[:200])
            # With json_response=True the streamable-HTTP transport
            # replies synchronously as application/json (no SSE stream).
            assert authed.headers.get("content-type", "").startswith("application/json"), (
                authed.headers.get("content-type")
            )
            # A successful initialize creates a session on the server.
            assert authed.headers.get("mcp-session-id"), authed.headers
        finally:
            await authed.aclose()


@pytest.mark.asyncio
async def test_app_exposes_mcp_at_documented_path(running_server: str) -> None:
    """Guard against regressions where /mcp gets double-prefixed to /mcp/mcp.

    The README documents ``http://localhost:8765/mcp`` as the client URL.
    A previous version mounted the inner app at ``/mcp`` which (combined
    with the inner app's own ``/mcp`` route) produced ``/mcp/mcp`` —
    anything hitting ``/mcp`` got 307 → 404. This test fails loudly if
    that regression returns.
    """
    async with httpx.AsyncClient(base_url=running_server) as client:
        r = await _post_mcp_headers(client, authed=True)
        try:
            assert r.status_code == 200, (r.status_code, r.text[:200])
        finally:
            await r.aclose()


def _tools_list_payload(session_id: str, id_: int = 2) -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "method": "tools/list",
        "params": {},
        "id": id_,
    }


def _tools_call_payload(
    name: str, arguments: dict[str, object], session_id: str, id_: int = 3
) -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
        "id": id_,
    }


def _mcp_headers(session_id: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Authorization": "Bearer test-token-0123456789",
        "Content-Type": "application/json",
    }
    if session_id:
        headers["mcp-session-id"] = session_id
    return headers


@pytest.mark.asyncio
async def test_mcp_server_registers_curated_tools(monkeypatch) -> None:
    """Wire-protocol layer: the registered MCP server answers tools/list.

    Uses the in-process memory transport to drive a full MCP handshake
    against the same server instance the HTTP layer exposes, verifying
    that the hand-written tools are all registered and discoverable.
    (Complements the HTTP-layer test which only verifies transport wiring.)
    """
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "test-token-0123456789")
    # Triggers create_app against the shared registry of curated tools.
    MaasmcpConfig.load(None)
    from maasmcp.registry import mcp

    async with Client(mcp, raise_exceptions=True) as session:
        result = await session.list_tools()
    names = {t.name for t in result.tools}
    assert "acquire_machine" in names, names
    assert "list_machines" in names, names
    assert "machines_read" in names, names
    assert len(result.tools) >= 5


@pytest.mark.asyncio
async def test_smoke_tool_call_against_mocked_maas(running_server: str) -> None:
    """Deployment smoke test: the real HTTP server can initialize an MCP
    session, list tools, and execute a read-only tool against MAAS.

    Catches runtime registration/signature breakages (like the earlier
    ``machine_delete`` ``params=`` TypeError) before the image is deployed.
    """
    async with httpx.AsyncClient(base_url=running_server) as client:
        # Initialize the MCP session first, before starting respx: respx's
        # global transport patch can interfere with response headers on the
        # local uvicorn socket, so we get a clean session id here.
        init = await _post_mcp_headers(client, authed=True)
        try:
            assert init.status_code == 200, (init.status_code, init.text[:200])
            session_id = init.headers["mcp-session-id"]
        finally:
            await init.aclose()

        # List tools before patching httpx so the local MCP transport is
        # unaffected by respx.
        tools = await client.post(
            "/mcp", json=_tools_list_payload(session_id), headers=_mcp_headers(session_id)
        )
        assert tools.status_code == 200, (tools.status_code, tools.text[:200])
        tools_body = tools.json()
        tool_names = {t["name"] for t in tools_body["result"]["tools"]}
        assert "machines_read" in tool_names, tool_names

        # Now mock only the upstream MAAS endpoint and execute the tool.
        # Add an explicit pass-through for local uvicorn traffic; respx's
        # global patch otherwise intercepts the /mcp tool-call and returns
        # an empty 200 response.
        with respx.mock(base_url="https://maas.example.com/MAAS", assert_all_mocked=False) as rs:
            rs.route(host="127.0.0.1").pass_through()
            rs.get("/api/2.0/machines/").mock(
                return_value=httpx.Response(200, json=[{"system_id": "abc", "hostname": "node-1"}])
            )

            # Call a read-only tool that hits the mocked MAAS endpoint.
            call = await client.post(
                "/mcp",
                json=_tools_call_payload("machines_read", {"paginate": False}, session_id),
                headers=_mcp_headers(session_id),
            )
            assert call.status_code == 200, (call.status_code, call.text[:200])
            call_body = call.json()
            assert "result" in call_body, call_body
            assert "error" not in call_body, call_body
            result = call_body["result"]
            assert result["content"], result
