import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.create_vlan import CreateVlanTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


async def test_create_vlan_happy(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.post("/api/2.0/fabrics/1/vlans/").mock(
            return_value=Response(200, json={"id": 10, "vid": 100, "fabric": 1})
        )
        async with maas_client:
            result = await CreateVlanTool().run(maas_client, vid=100, fabric_id=1, confirm=True)
    assert result == {"id": 10, "vid": 100, "fabric": 1}
    assert route.called


async def test_create_vlan_requires_confirm(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="confirm=True"):
            await CreateVlanTool().run(maas_client, vid=100, fabric_id=1, confirm=False)


@pytest.mark.parametrize("vid", [0, -1, 4095, 10000])
async def test_create_vlan_vid_out_of_range(monkeypatch, vid):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="vid"):
            await CreateVlanTool().run(maas_client, vid=vid, fabric_id=1, confirm=True)


async def test_create_vlan_invalid_fabric_raises(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="fabric_id"):
            # fabric-0 is the legitimate default fabric; only negatives are rejected
            await CreateVlanTool().run(maas_client, vid=100, fabric_id=-1, confirm=True)


async def test_create_vlan_non_dict_raises(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.post("/api/2.0/fabrics/1/vlans/").mock(return_value=Response(200, json="bad"))
        async with maas_client:
            with pytest.raises(ValueError, match="non-dict"):
                await CreateVlanTool().run(maas_client, vid=100, fabric_id=1, confirm=True)


async def test_create_vlan_409_propagates(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.post("/api/2.0/fabrics/1/vlans/").mock(return_value=Response(409, text="dup vid"))
        async with maas_client:
            with pytest.raises(Exception) as exc_info:
                await CreateVlanTool().run(maas_client, vid=100, fabric_id=1, confirm=True)
    assert "409" in str(exc_info.value)
