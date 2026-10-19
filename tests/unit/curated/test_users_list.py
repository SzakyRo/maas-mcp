import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.users_list import UsersListTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


async def test_users_list_happy(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    page = [{"username": "alice"}, {"username": "bob"}]
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.get("/api/2.0/users/").mock(return_value=Response(200, json=page))
        async with maas_client:
            result = await UsersListTool().run(maas_client)
    assert route.called
    assert "paginate" not in str(route.calls.last.request.url)
    assert result == page
