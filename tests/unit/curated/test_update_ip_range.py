import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.update_ip_range import UpdateIpRangeTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


async def test_update_ip_range_happy(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.put("/api/2.0/ipranges/3/").mock(
            return_value=Response(200, json={"id": 3, "comment": "updated"})
        )
        async with maas_client:
            result = await UpdateIpRangeTool().run(
                maas_client, ip_range_id=3, comment="updated", confirm=True
            )
    assert result == {"id": 3, "comment": "updated"}
    assert route.called


async def test_update_ip_range_requires_confirm(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="confirm=True"):
            await UpdateIpRangeTool().run(maas_client, ip_range_id=3, comment="x", confirm=False)
