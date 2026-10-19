"""ip_address_reserve: op-reserve with confirm gate."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.ip_address_reserve import IpAddressReserveTool
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


async def test_reserve_specific_ip_happy(monkeypatch):
    maas_client = _client(monkeypatch)
    payload = {"ip": "10.72.91.155", "alloc_type": 4}
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.post("/api/2.0/ipaddresses/op-reserve").mock(
            return_value=Response(200, json=payload)
        )
        async with maas_client:
            result = await IpAddressReserveTool().run(maas_client, ip="10.72.91.155", confirm=True)
    assert route.called
    assert result == payload


async def test_reserve_requires_subnet_or_ip(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        async with maas_client:
            with pytest.raises(ValueError, match="requires subnet"):
                await IpAddressReserveTool().run(maas_client, confirm=True)
    assert not mock.calls


async def test_reserve_requires_confirm(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await IpAddressReserveTool().run(maas_client, ip="10.72.91.155", confirm=False)
    assert not mock.calls


async def test_reserve_non_dict_raises(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.post("/api/2.0/ipaddresses/op-reserve").mock(return_value=Response(200, json="bad"))
        async with maas_client:
            with pytest.raises(ValueError, match="non-dict"):
                await IpAddressReserveTool().run(maas_client, subnet="10.1.2.0/24", confirm=True)
