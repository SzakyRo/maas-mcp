import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.get_subnet import GetSubnetTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


async def test_get_subnet_happy(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.get("/api/2.0/subnets/3/").mock(
            return_value=Response(200, json={"id": 3, "cidr": "10.0.0.0/24"})
        )
        async with maas_client:
            result = await GetSubnetTool().run(maas_client, subnet_id=3)
    assert result == {"id": 3, "cidr": "10.0.0.0/24"}


async def test_get_subnet_invalid_id_raises(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="subnet_id"):
            await GetSubnetTool().run(maas_client, subnet_id=0)


async def test_get_subnet_non_dict_raises(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.get("/api/2.0/subnets/3/").mock(return_value=Response(200, json=["unexpected"]))
        async with maas_client:
            with pytest.raises(ValueError, match="non-dict"):
                await GetSubnetTool().run(maas_client, subnet_id=3)
