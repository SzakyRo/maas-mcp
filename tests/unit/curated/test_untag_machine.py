"""untag_machine: hostname OR system_id (now both optional) — resolver path."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.untag_machine import UntagMachineTool
from maasmcp.maas.client import MaasClient


async def test_untag_machine_by_system_id_skips_hostname_lookup(monkeypatch) -> None:
    """system_id-only path MUST NOT touch /machines/?hostname=."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        resolve_route = mock.get(
            "/api/2.0/machines/", params={"hostname": "node-1"}
        ).mock(return_value=Response(200, json=[]))
        tag_route = mock.post("/api/2.0/tags/fast/op-update_nodes").mock(
            return_value=Response(200, json={})
        )
        async with maas_client:
            await UntagMachineTool().run(
                maas_client, tag="fast", system_id="aa1", confirm=True
            )
    assert not resolve_route.called
    assert tag_route.call_count == 1
    body = tag_route.calls.last.request.content.decode()
    assert 'name="remove"' in body
    assert "\r\naa1\r\n" in body


async def test_untag_machine_by_hostname_still_works(monkeypatch) -> None:
    """Backwards compat: hostname-only call still resolves and untags."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        resolve_route = mock.get(
            "/api/2.0/machines/", params={"hostname": "node-1"}
        ).mock(return_value=Response(200, json=[{"system_id": "xy7zab"}]))
        tag_route = mock.post("/api/2.0/tags/fast/op-update_nodes").mock(
            return_value=Response(200, json={})
        )
        async with maas_client:
            await UntagMachineTool().run(
                maas_client, hostname="node-1", tag="fast", confirm=True
            )
    assert resolve_route.call_count == 1
    assert tag_route.call_count == 1
    body = tag_route.calls.last.request.content.decode()
    assert 'name="remove"' in body
    assert "\r\nxy7zab\r\n" in body


async def test_untag_machine_requires_confirm(monkeypatch) -> None:
    """confirm=False raises before any HTTP call (confirm gate first)."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await UntagMachineTool().run(
                    maas_client, tag="fast", system_id="aa1", confirm=False
                )
    assert not mock.calls


async def test_untag_machine_hostname_miss_raises(monkeypatch) -> None:
    """Hostname that doesn't resolve → ValueError (after confirm gate)."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        mock.get("/api/2.0/machines/").mock(return_value=Response(200, json=[]))
        async with maas_client:
            with pytest.raises(ValueError, match="no machine found"):
                await UntagMachineTool().run(
                    maas_client, hostname="ghost", tag="fast", confirm=True
                )


async def test_untag_machine_both_none_raises(monkeypatch) -> None:
    """Neither system_id nor hostname → ValueError from the resolver."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        async with maas_client:
            with pytest.raises(ValueError, match="at least one of system_id or hostname"):
                await UntagMachineTool().run(maas_client, tag="fast", confirm=True)
    assert not mock.calls
