import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.create_subnet import CreateSubnetTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


async def test_create_subnet_happy(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.post("/api/2.0/subnets/").mock(
            return_value=Response(200, json={"id": 5, "cidr": "10.0.0.0/24"})
        )
        async with maas_client:
            result = await CreateSubnetTool().run(
                maas_client, cidr="10.0.0.0/24", fabric_id=1, confirm=True
            )
    assert result == {"id": 5, "cidr": "10.0.0.0/24"}
    assert route.called


async def test_create_subnet_requires_confirm(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="confirm=True"):
            await CreateSubnetTool().run(maas_client, cidr="10.0.0.0/24", confirm=False)


@pytest.mark.parametrize(
    "bad_cidr",
    ["not-a-cidr", "10.0.0", "10.0.0.0/33", "", "10.0.0.5/24"],
)
async def test_create_subnet_invalid_cidr(monkeypatch, bad_cidr):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="cidr"):
            await CreateSubnetTool().run(maas_client, cidr=bad_cidr, fabric_id=1, confirm=True)


async def test_create_subnet_invalid_fabric(monkeypatch):
    """Negative fabric ids are rejected; 0 is LEGAL (MAAS fabric-0 is the
    default fabric) and must not raise here."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="fabric_id"):
            await CreateSubnetTool().run(
                maas_client, cidr="10.0.0.0/24", fabric_id=-1, confirm=True
            )


async def test_create_subnet_non_dict_raises(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.post("/api/2.0/subnets/").mock(return_value=Response(200, json="bad"))
        async with maas_client:
            with pytest.raises(ValueError, match="non-dict"):
                await CreateSubnetTool().run(
                    maas_client, cidr="10.0.0.0/24", fabric_id=1, confirm=True
                )


async def test_create_subnet_409_propagates(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.post("/api/2.0/subnets/").mock(return_value=Response(409, text="dup"))
        async with maas_client:
            with pytest.raises(Exception) as exc_info:
                await CreateSubnetTool().run(
                    maas_client, cidr="10.0.0.0/24", fabric_id=1, confirm=True
                )
    assert "409" in str(exc_info.value)
