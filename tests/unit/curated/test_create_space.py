import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.create_space import CreateSpaceTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


async def test_create_space_happy(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.post("/api/2.0/spaces/").mock(
            return_value=Response(200, json={"id": 4, "name": "newspace"})
        )
        async with maas_client:
            result = await CreateSpaceTool().run(maas_client, name="newspace", confirm=True)
    assert result == {"id": 4, "name": "newspace"}
    assert route.called


async def test_create_space_requires_confirm(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="confirm=True"):
            await CreateSpaceTool().run(maas_client, name="x", confirm=False)


async def test_create_space_non_dict_raises(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.post("/api/2.0/spaces/").mock(return_value=Response(200, json="bad"))
        async with maas_client:
            with pytest.raises(ValueError, match="non-dict"):
                await CreateSpaceTool().run(maas_client, name="x", confirm=True)


async def test_create_space_409_propagates(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.post("/api/2.0/spaces/").mock(return_value=Response(409, text="dup"))
        async with maas_client:
            with pytest.raises(Exception) as exc_info:
                await CreateSpaceTool().run(maas_client, name="dup", confirm=True)
    assert "409" in str(exc_info.value)
