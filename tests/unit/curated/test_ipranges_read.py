import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.ipranges_read import IprangesReadTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


async def test_ipranges_read_returns_page(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        route = mock.get("/api/2.0/ipranges/").mock(
            return_value=Response(
                200,
                json=[{"id": 3, "start_ip": "10.0.0.10", "end_ip": "10.0.0.20"}],
            )
        )
        async with maas_client:
            result = await IprangesReadTool().run(maas_client)
    assert route.called
    assert result == [{"id": 3, "start_ip": "10.0.0.10", "end_ip": "10.0.0.20"}]
    assert "paginate" not in route.calls[0].request.url.params
