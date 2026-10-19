"""ip_addresses_read: list/filter IP addresses (read-only)."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.ip_addresses_read import IpAddressesReadTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


def _client(monkeypatch: pytest.MonkeyPatch) -> MaasClient:
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    return maas_client


async def test_ip_addresses_read_happy(monkeypatch):
    maas_client = _client(monkeypatch)
    page = [{"ip": "10.72.91.155", "alloc_type": 4}]
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.get("/api/2.0/ipaddresses/").mock(return_value=Response(200, json=page))
        async with maas_client:
            result = await IpAddressesReadTool().run(maas_client)
    assert route.called
    assert "paginate" not in str(route.calls.last.request.url)
    assert result == page


async def test_ip_addresses_read_ip_filter(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.get("/api/2.0/ipaddresses/").mock(return_value=Response(200, json=[]))
        async with maas_client:
            result = await IpAddressesReadTool().run(maas_client, ip="10.72.91.155")
    assert route.calls.last.request.url.params["ip"] == "10.72.91.155"
    assert result == []


async def test_ip_addresses_read_all_param_goes_to_admin_view(monkeypatch):
    """Default MAAS listing hides reservations owned by others; all=True
    is the admin escape hatch — it must reach the wire."""
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.get("/api/2.0/ipaddresses/").mock(return_value=Response(200, json=[]))
        async with maas_client:
            await IpAddressesReadTool().run(maas_client, all=True, owner="admin")
    params = route.calls.last.request.url.params
    assert "all" in params
    assert params["owner"] == "admin"
