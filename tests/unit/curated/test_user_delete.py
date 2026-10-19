import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.user_delete import UserDeleteTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


async def test_user_delete_happy(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.delete("/api/2.0/users/bob/").mock(return_value=Response(204))
        async with maas_client:
            result = await UserDeleteTool().run(maas_client, username="bob", confirm=True)
    assert route.called
    assert "transfer_resources_to" not in str(route.calls.last.request.url)
    assert "confirm" not in str(route.calls.last.request.url)
    assert result is None


async def test_user_delete_transfer_resources_to_query_string(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.delete("/api/2.0/users/bob/").mock(return_value=Response(204))
        async with maas_client:
            result = await UserDeleteTool().run(
                maas_client, username="bob", transfer_resources_to="alice", confirm=True
            )
    assert route.called
    assert "transfer_resources_to=alice" in str(route.calls.last.request.url)
    assert "confirm" not in str(route.calls.last.request.url)
    assert result is None


async def test_user_delete_requires_confirm(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        route = mock.delete("/api/2.0/users/bob/").mock(return_value=Response(204))
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await UserDeleteTool().run(maas_client, username="bob", confirm=False)
            with pytest.raises(ValueError, match="confirm=True"):
                await UserDeleteTool().run(maas_client, username="bob")
    assert not route.called
