import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.create_interface import CreateInterfaceTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


def _client(monkeypatch: pytest.MonkeyPatch) -> MaasClient:
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    return maas_client


async def test_create_interface_happy(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.post("/api/2.0/nodes/abc123/interfaces/op-create_physical").mock(
            return_value=Response(200, json={"id": 12, "name": "eth1"})
        )
        async with maas_client:
            result = await CreateInterfaceTool().run(
                maas_client, system_id="abc123", mac_address="52:54:00:12:34:56", confirm=True
            )
    assert result == {"id": 12, "name": "eth1"}
    assert route.called
    body = route.calls.last.request.content.decode(errors="replace")
    assert 'name="mac_address"' in body


async def test_create_interface_requires_confirm(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await CreateInterfaceTool().run(
                    maas_client,
                    system_id="abc123",
                    mac_address="52:54:00:12:34:56",
                    confirm=False,
                )
    assert not mock.calls


async def test_create_interface_empty_system_id(monkeypatch):
    maas_client = _client(monkeypatch)
    async with maas_client:
        with pytest.raises(ValueError, match="system_id"):
            await CreateInterfaceTool().run(
                maas_client,
                system_id="",
                mac_address="52:54:00:12:34:56",
                name="eth1",
                confirm=True,
            )


async def test_create_interface_non_dict_raises(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.post("/api/2.0/nodes/abc123/interfaces/op-create_physical").mock(
            return_value=Response(200, json="bad")
        )
        async with maas_client:
            with pytest.raises(ValueError, match="non-dict"):
                await CreateInterfaceTool().run(
                    maas_client, system_id="abc123", mac_address="52:54:00:12:34:56", confirm=True
                )


async def test_create_interface_409_propagates(monkeypatch):
    maas_client = _client(monkeypatch)
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.post("/api/2.0/nodes/abc123/interfaces/op-create_physical").mock(
            return_value=Response(409, text="dup")
        )
        async with maas_client:
            with pytest.raises(Exception) as exc_info:
                await CreateInterfaceTool().run(
                    maas_client, system_id="abc123", mac_address="52:54:00:12:34:56", confirm=True
                )
    assert "409" in str(exc_info.value)
