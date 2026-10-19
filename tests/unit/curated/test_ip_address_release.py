"""ip_address_release: op-release with confirm gate and force/discovered rules."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.ip_address_release import IpAddressReleaseTool
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


async def test_release_happy_204_returns_none(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.post("/api/2.0/ipaddresses/op-release").mock(return_value=Response(204))
        async with maas_client:
            result = await IpAddressReleaseTool().run(maas_client, ip="10.72.91.155", confirm=True)
    assert route.called
    assert result is None


async def test_release_force_body(monkeypatch):
    """force/discovered must reach the wire when set (other-owner rows are
    only releasable this way — verified live against MAAS 0.8.2-era)."""
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.post("/api/2.0/ipaddresses/op-release").mock(return_value=Response(204))
        async with maas_client:
            await IpAddressReleaseTool().run(
                maas_client, ip="10.72.91.155", force=True, discovered=True, confirm=True
            )
    body = route.calls.last.request.content.decode(errors="replace")
    assert 'name="force"' in body
    assert 'name="discovered"' in body


async def test_release_requires_confirm(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await IpAddressReleaseTool().run(maas_client, ip="10.72.91.155", confirm=False)
    assert not mock.calls


async def test_release_discovered_without_force_raises(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        async with maas_client:
            with pytest.raises(ValueError, match="force"):
                await IpAddressReleaseTool().run(
                    maas_client, ip="10.72.91.155", discovered=True, confirm=True
                )
    assert not mock.calls
