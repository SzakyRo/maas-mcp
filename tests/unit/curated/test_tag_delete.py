import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.tag_delete import TagDeleteTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


async def test_tag_delete_happy(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.delete("/api/2.0/tags/my-tag/").mock(return_value=Response(204))
        async with maas_client:
            result = await TagDeleteTool().run(maas_client, name="my-tag", confirm=True)
    assert route.called
    assert "confirm" not in str(route.calls.last.request.url)
    assert result is None


async def test_tag_delete_requires_confirm(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        route = mock.delete("/api/2.0/tags/my-tag/").mock(return_value=Response(204))
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await TagDeleteTool().run(maas_client, name="my-tag", confirm=False)
            with pytest.raises(ValueError, match="confirm=True"):
                await TagDeleteTool().run(maas_client, name="my-tag")
    assert not route.called
