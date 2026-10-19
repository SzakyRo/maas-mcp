"""End-to-end tool calls through the MCP protocol and the rebind layer.

test_http_transport.py proves tools/list works; this file proves the actual
call path works: MCP session → rebound wrapper (client injected at call
time from the singleton) → respx-mocked MAAS upstream. This is the layer the
c07d0cd confirm-gate and pagination changes live in, and the only place a
tool-signature drift would be visible without a live MAAS.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from mcp import Client

from maasmcp.config import MaasmcpConfig
from maasmcp.curated._catalog import EXPECTED_DOMAINS
from maasmcp.maas.client import MaasClient
from maasmcp.maas.singleton import set_shared_client


@pytest.fixture
def mcp_session_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "test-token-0123456789")
    cfg = MaasmcpConfig.load(None)
    from maasmcp.registry import mcp

    return cfg, mcp


@pytest.mark.asyncio
async def test_tools_call_runs_rebound_tool_end_to_end(mcp_session_env) -> None:
    """power_status over the MCP protocol: client injection, upstream call,
    and result plumbing all work."""
    cfg, mcp = mcp_session_env
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get("https://maas.example.com/MAAS/api/2.0/machines/abc/").mock(
            return_value=httpx.Response(200, json={"power_state": "on"})
        )
        client = MaasClient(cfg)
        async with client:
            set_shared_client(client)
            try:
                async with Client(mcp, raise_exceptions=True) as session:
                    result = await session.call_tool("power_status", {"system_id": "abc"})
            finally:
                set_shared_client(None)
    assert route.called
    assert not result.is_error
    texts = [c.text for c in result.content if getattr(c, "text", None)]
    assert "on" in texts


@pytest.mark.asyncio
async def test_tools_call_confirm_gate_fires_over_protocol(mcp_session_env) -> None:
    """A destructive tool called without confirm fails with an error result
    BEFORE any HTTP call leaves the process."""
    cfg, mcp = mcp_session_env
    with respx.mock(assert_all_called=False) as mock:
        client = MaasClient(cfg)
        async with client:
            set_shared_client(client)
            try:
                async with Client(mcp, raise_exceptions=True) as session:
                    result = await session.call_tool(
                        "power_control", {"system_id": "abc", "action": "off"}
                    )
            finally:
                set_shared_client(None)
    assert result.is_error
    texts = [c.text for c in result.content if getattr(c, "text", None)]
    assert any("confirm=True" in t for t in texts), texts
    assert not mock.calls


@pytest.mark.asyncio
async def test_tools_index_returns_catalog_over_protocol(mcp_session_env) -> None:
    """The tools_index helper works end-to-end and returns grouped domains."""
    cfg, mcp = mcp_session_env
    client = MaasClient(cfg)
    async with client:
        set_shared_client(client)
        try:
            async with Client(mcp, raise_exceptions=True) as session:
                result = await session.call_tool("tools_index", {})
        finally:
            set_shared_client(None)
    assert not result.is_error
    texts = [c.text for c in result.content if getattr(c, "text", None)]
    payload = json.loads(texts[0])
    assert "groups" in payload
    assert set(payload["groups"]) == EXPECTED_DOMAINS
    assert any(entry["name"] == "tools_index" for entry in payload["groups"]["meta"])
