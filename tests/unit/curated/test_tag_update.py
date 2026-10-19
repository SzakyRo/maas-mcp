import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.tag_update import TagUpdateTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


async def test_tag_update_happy(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.put("/api/2.0/tags/my-tag/").mock(
            return_value=Response(200, json={"name": "my-tag", "comment": "docs"})
        )
        async with maas_client:
            result = await TagUpdateTool().run(
                maas_client, name="my-tag", comment="docs", confirm=True
            )
    assert route.called
    body = route.calls.last.request.content
    assert b'name="comment"' in body
    assert b'name="definition"' not in body
    assert b'name="confirm"' not in body
    assert result == {"name": "my-tag", "comment": "docs"}


async def test_tag_update_requires_confirm(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        route = mock.put("/api/2.0/tags/my-tag/").mock(return_value=Response(200, json={}))
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await TagUpdateTool().run(maas_client, name="my-tag", comment="x", confirm=False)
    assert not route.called
