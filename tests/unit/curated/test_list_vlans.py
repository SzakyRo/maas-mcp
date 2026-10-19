import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.list_vlans import ListVlansTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


async def test_list_vlans_unwraps(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.get("/api/2.0/fabrics/1/vlans/").mock(
            return_value=Response(200, json={"vlans": [{"id": 1, "vid": 10}]})
        )
        async with maas_client:
            result = await ListVlansTool().run(maas_client, fabric_id=1)
    assert result == [{"id": 1, "vid": 10}]


async def test_list_vlans_bare_list(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.get("/api/2.0/fabrics/1/vlans/").mock(return_value=Response(200, json=[{"id": 2}]))
        async with maas_client:
            result = await ListVlansTool().run(maas_client, fabric_id=1)
    assert result == [{"id": 2}]
