import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.update_fabric import UpdateFabricTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


async def test_update_fabric_happy(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.put("/api/2.0/fabrics/3/").mock(
            return_value=Response(200, json={"id": 3, "name": "renamed"})
        )
        async with maas_client:
            result = await UpdateFabricTool().run(
                maas_client, fabric_id=3, name="renamed", confirm=True
            )
    assert result == {"id": 3, "name": "renamed"}
    assert route.called


async def test_update_fabric_requires_confirm(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="confirm=True"):
            await UpdateFabricTool().run(maas_client, fabric_id=3, name="x", confirm=False)
