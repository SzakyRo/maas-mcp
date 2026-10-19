import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.machines_set_zone import MachinesSetZoneTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


async def test_machines_set_zone_requires_confirm(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        route = mock.post("/api/2.0/machines/?op=set_zone").mock(
            return_value=Response(200, json={})
        )
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await MachinesSetZoneTool().run(maas_client, zone="az1", nodes="abc")
    assert not route.called


async def test_machines_set_zone_happy(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        route = mock.post("/api/2.0/machines/?op=set_zone").mock(
            return_value=Response(200, json={"status_name": "Ready"})
        )
        async with maas_client:
            result = await MachinesSetZoneTool().run(
                maas_client, zone="az1", nodes="abc", confirm=True
            )
    assert route.call_count == 1
    body = route.calls.last.request.content.decode()
    assert 'name="zone"' in body and "az1" in body
    assert 'name="nodes"' in body and "abc" in body
    assert 'name="confirm"' not in body
    assert result == {"status_name": "Ready"}


async def test_machines_set_zone_by_hostname(monkeypatch):
    """Hostname triggers one /machines/?hostname= GET, then POSTs the
    resolved system_id as `nodes=`. Existing tests still pass `nodes=`
    directly — both forms resolve to the same upstream POST body."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        resolve_route = mock.get(
            "/api/2.0/machines/", params={"hostname": "node-1"}
        ).mock(return_value=Response(200, json=[{"system_id": "xy7zab", "hostname": "node-1"}]))
        post_route = mock.post("/api/2.0/machines/?op=set_zone").mock(
            return_value=Response(200, json={"status_name": "Ready"})
        )
        async with maas_client:
            result = await MachinesSetZoneTool().run(
                maas_client, zone="az1", hostname="node-1", confirm=True
            )
    assert resolve_route.call_count == 1
    assert post_route.call_count == 1
    body = post_route.calls.last.request.content.decode()
    assert 'name="zone"' in body and "az1" in body
    assert 'name="nodes"' in body and "xy7zab" in body
    assert result == {"status_name": "Ready"}


async def test_machines_set_zone_both_none_raises(monkeypatch):
    """Neither nodes nor hostname → ValueError (resolve_system_id raises)."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        async with maas_client:
            with pytest.raises(ValueError, match="at least one of system_id or hostname"):
                await MachinesSetZoneTool().run(maas_client, zone="az1", confirm=True)
    assert not mock.calls
