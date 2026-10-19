import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.users_create import UsersCreateTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


async def test_users_create_happy(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        route = mock.post("/api/2.0/users/").mock(
            return_value=Response(200, json={"username": "bob"})
        )
        async with maas_client:
            result = await UsersCreateTool().run(
                maas_client,
                username="bob",
                email="bob@example.com",
                password="secret",
                is_superuser=False,
                confirm=True,
            )
    assert route.called
    body = route.calls.last.request.content
    assert b'name="username"' in body
    assert b'name="email"' in body
    assert b'name="password"' in body
    assert b'name="is_superuser"' in body
    assert b'name="confirm"' not in body
    assert result == {"username": "bob"}


async def test_users_create_requires_confirm(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        route = mock.post("/api/2.0/users/").mock(return_value=Response(200, json={}))
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await UsersCreateTool().run(
                    maas_client,
                    username="bob",
                    email="bob@example.com",
                    password="secret",
                    is_superuser=False,
                    confirm=False,
                )
            with pytest.raises(ValueError, match="confirm=True"):
                await UsersCreateTool().run(
                    maas_client,
                    username="bob",
                    email="bob@example.com",
                    password="secret",
                    is_superuser=False,
                )
    assert not route.called
