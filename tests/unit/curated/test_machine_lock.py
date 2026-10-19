import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.machine_lock import MachineLockTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


async def test_machine_lock_requires_confirm(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        route = mock.post("/api/2.0/machines/abc/?op=lock").mock(
            return_value=Response(200, json={})
        )
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await MachineLockTool().run(maas_client, system_id="abc", confirm=False)
    assert not route.called


async def test_machine_lock_happy(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        route = mock.post("/api/2.0/machines/abc/?op=lock").mock(
            return_value=Response(200, json={"system_id": "abc"})
        )
        async with maas_client:
            result = await MachineLockTool().run(
                maas_client, system_id="abc", comment="maintenance", confirm=True
            )
    assert route.call_count == 1
    body = route.calls.last.request.content.decode()
    assert 'name="comment"' in body
    assert "maintenance" in body
    assert 'name="confirm"' not in body
    assert result == {"system_id": "abc"}
