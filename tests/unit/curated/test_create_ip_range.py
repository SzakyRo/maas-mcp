import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.create_ip_range import CreateIpRangeTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


async def test_create_ip_range_happy(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.post("/api/2.0/ipranges/").mock(
            return_value=Response(200, json={"id": 7, "start_ip": "10.0.0.10"})
        )
        async with maas_client:
            result = await CreateIpRangeTool().run(
                maas_client,
                subnet_id=5,
                start_ip="10.0.0.10",
                end_ip="10.0.0.20",
                confirm=True,
            )
    assert result == {"id": 7, "start_ip": "10.0.0.10"}
    assert route.called


async def test_create_ip_range_requires_confirm(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="confirm=True"):
            await CreateIpRangeTool().run(
                maas_client,
                subnet_id=5,
                start_ip="10.0.0.10",
                end_ip="10.0.0.20",
                confirm=False,
            )


@pytest.mark.parametrize("bad_ip", ["not-an-ip", "10.0.0", "256.0.0.1", ""])
async def test_create_ip_range_invalid_start(monkeypatch, bad_ip):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="start_ip"):
            await CreateIpRangeTool().run(
                maas_client,
                subnet_id=5,
                start_ip=bad_ip,
                end_ip="10.0.0.20",
                confirm=True,
            )


async def test_create_ip_range_end_before_start(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="start_ip"):
            await CreateIpRangeTool().run(
                maas_client,
                subnet_id=5,
                start_ip="10.0.0.20",
                end_ip="10.0.0.10",
                confirm=True,
            )


async def test_create_ip_range_non_dict_raises(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.post("/api/2.0/ipranges/").mock(return_value=Response(200, json="bad"))
        async with maas_client:
            with pytest.raises(ValueError, match="non-dict"):
                await CreateIpRangeTool().run(
                    maas_client,
                    subnet_id=5,
                    start_ip="10.0.0.10",
                    end_ip="10.0.0.20",
                    confirm=True,
                )
