import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.tags_create import TagsCreateTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


async def test_tags_create_happy(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.post("/api/2.0/tags/").mock(return_value=Response(200, json={"name": "gpu"}))
        async with maas_client:
            result = await TagsCreateTool().run(
                maas_client, name="gpu", kernel_opts="nomodeset", confirm=True
            )
    assert route.called
    body = route.calls.last.request.content
    assert b'name="name"' in body
    assert b'name="kernel_opts"' in body
    assert b'name="comment"' not in body
    assert b'name="confirm"' not in body
    assert result == {"name": "gpu"}


async def test_tags_create_requires_confirm(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        route = mock.post("/api/2.0/tags/").mock(return_value=Response(200, json={}))
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await TagsCreateTool().run(maas_client, name="gpu", confirm=False)
            with pytest.raises(ValueError, match="confirm=True"):
                await TagsCreateTool().run(maas_client, name="gpu")
    assert not route.called
