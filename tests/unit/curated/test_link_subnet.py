"""link_subnet: POST op-link_subnet with confirm gate."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.link_subnet import LinkSubnetTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


async def test_link_subnet_static_happy(monkeypatch):
    """mode=STATIC with ip_address — the bond0.79 + 10.112.128.50 case."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.post("/api/2.0/nodes/abc123/interfaces/10/op-link_subnet").mock(
            return_value=Response(
                200,
                json={
                    "id": 10,
                    "links": [{"id": 12, "mode": "static", "ip_address": "10.112.128.50"}],
                },
            )
        )
        async with maas_client:
            result = await LinkSubnetTool().run(
                maas_client,
                system_id="abc123",
                iface_id=10,
                subnet_id=1,
                mode="STATIC",
                ip_address="10.112.128.50",
                confirm=True,
            )
    assert result["id"] == 10
    assert route.called
    sent_body = route.calls.last.request.read().decode()
    assert 'name="subnet"' in sent_body
    assert 'name="mode"' in sent_body
    assert "STATIC" in sent_body
    assert 'name="ip_address"' in sent_body
    assert "10.112.128.50" in sent_body


async def test_link_subnet_auto_omits_ip_address(monkeypatch):
    """mode=AUTO must NOT include an ip_address field."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.post("/api/2.0/nodes/abc123/interfaces/10/op-link_subnet").mock(
            return_value=Response(200, json={"id": 10})
        )
        async with maas_client:
            await LinkSubnetTool().run(
                maas_client,
                system_id="abc123",
                iface_id=10,
                subnet_id=1,
                mode="AUTO",
                confirm=True,
            )
    sent_body = route.calls.last.request.read().decode()
    assert 'name="mode"' in sent_body
    assert "AUTO" in sent_body
    assert 'name="ip_address"' not in sent_body


async def test_link_subnet_static_without_ip_auto_selects(monkeypatch):
    """mode=STATIC without ip_address is valid — MAAS auto-selects an IP from
    the subnet (spec: "If not provided an IP address from subnet will be auto
    selected")."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.post("/api/2.0/nodes/abc123/interfaces/10/op-link_subnet").mock(
            return_value=Response(200, json={"id": 10})
        )
        async with maas_client:
            result = await LinkSubnetTool().run(
                maas_client,
                system_id="abc123",
                iface_id=10,
                subnet_id=1,
                mode="STATIC",
                confirm=True,
            )
    assert result == {"id": 10}
    assert route.called
    sent = route.calls.last.request.read().decode()
    assert 'name="mode"' in sent and "STATIC" in sent
    assert 'name="ip_address"' not in sent


async def test_link_subnet_dhcp_mode(monkeypatch):
    """DHCP is a distinct MAAS link mode and must reach the wire."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.post("/api/2.0/nodes/abc123/interfaces/10/op-link_subnet").mock(
            return_value=Response(200, json={"id": 10})
        )
        async with maas_client:
            await LinkSubnetTool().run(
                maas_client,
                system_id="abc123",
                iface_id=10,
                subnet_id=1,
                mode="DHCP",
                confirm=True,
            )
    assert route.called
    sent = route.calls.last.request.read().decode()
    assert "DHCP" in sent


async def test_link_subnet_rejects_ip_with_non_static(monkeypatch):
    """ip_address is meaningful only with mode=STATIC."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="only meaningful with mode=STATIC"):
            await LinkSubnetTool().run(
                maas_client,
                system_id="abc123",
                iface_id=10,
                subnet_id=1,
                mode="AUTO",
                ip_address="10.0.0.1",
                confirm=True,
            )


async def test_link_subnet_invalid_mode(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="mode must be one of"):
            await LinkSubnetTool().run(
                maas_client,
                system_id="abc123",
                iface_id=10,
                subnet_id=1,
                mode="BOGUS",
                confirm=True,
            )


async def test_link_subnet_requires_confirm(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="confirm=True"):
            await LinkSubnetTool().run(
                maas_client,
                system_id="abc123",
                iface_id=10,
                subnet_id=1,
                mode="AUTO",
                confirm=False,
            )


async def test_link_subnet_default_gateway_included(monkeypatch):
    """default_gateway=True should appear in the multipart body."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.post("/api/2.0/nodes/abc123/interfaces/10/op-link_subnet").mock(
            return_value=Response(200, json={"id": 10})
        )
        async with maas_client:
            await LinkSubnetTool().run(
                maas_client,
                system_id="abc123",
                iface_id=10,
                subnet_id=1,
                mode="STATIC",
                ip_address="10.0.0.1",
                default_gateway=True,
                confirm=True,
            )
    sent_body = route.calls.last.request.read().decode()
    assert 'name="default_gateway"' in sent_body
    assert "true" in sent_body


async def test_link_subnet_by_hostname(maas_client: MaasClient) -> None:
    """Hostname path: resolve then byte-identical upstream POST.

    Proves the hostname→system_id resolve happens and the actual upstream
    call shape is unchanged from the system_id path.
    """
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        resolve_route = mock.get(
            "/api/2.0/machines/", params={"hostname": "node-1"}
        ).mock(return_value=Response(200, json=[{"system_id": "xy7zab"}]))
        link_route = mock.post(
            "/api/2.0/nodes/xy7zab/interfaces/10/op-link_subnet"
        ).mock(return_value=Response(200, json={"id": 10}))
        async with maas_client:
            result = await LinkSubnetTool().run(
                maas_client,
                hostname="node-1",
                iface_id=10,
                subnet_id=1,
                mode="AUTO",
                confirm=True,
            )
    assert resolve_route.call_count == 1
    assert link_route.call_count == 1
    assert result["id"] == 10


async def test_link_subnet_non_dict_raises(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.post("/api/2.0/nodes/abc123/interfaces/10/op-link_subnet").mock(
            return_value=Response(200, json="bad")
        )
        async with maas_client:
            with pytest.raises(ValueError, match="non-dict"):
                await LinkSubnetTool().run(
                    maas_client,
                    system_id="abc123",
                    iface_id=10,
                    subnet_id=1,
                    mode="AUTO",
                    confirm=True,
                )
