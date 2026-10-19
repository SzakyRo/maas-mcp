import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.list_ip_ranges import ListIpRangesTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


async def test_list_ip_ranges_unwraps(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.get("/api/2.0/ipranges/").mock(
            return_value=Response(200, json={"ipranges": [{"id": 1, "start_ip": "10.0.0.1"}]})
        )
        async with maas_client:
            result = await ListIpRangesTool().run(maas_client)
    assert result == [{"id": 1, "start_ip": "10.0.0.1"}]


async def test_list_ip_ranges_bare_list(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.get("/api/2.0/ipranges/").mock(return_value=Response(200, json=[{"id": 2}]))
        async with maas_client:
            result = await ListIpRangesTool().run(maas_client)
    assert result == [{"id": 2}]
