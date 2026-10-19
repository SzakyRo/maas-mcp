import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.machines_accept import MachinesAcceptTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


async def test_machines_accept_requires_confirm(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        route = mock.post("/api/2.0/machines/?op=accept").mock(return_value=Response(200, json={}))
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await MachinesAcceptTool().run(maas_client, machines=["abc", "def"])
    assert not route.called


async def test_machines_accept_happy(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        route = mock.post("/api/2.0/machines/?op=accept").mock(
            return_value=Response(200, json=[{"system_id": "abc"}])
        )
        async with maas_client:
            result = await MachinesAcceptTool().run(
                maas_client, machines=["abc"], confirm=True
            )
    assert route.call_count == 1
    body = route.calls.last.request.content.decode()
    assert 'name="machines"' in body
    assert "abc" in body
    assert result == [{"system_id": "abc"}]


async def test_machines_accept_both_none_raises(monkeypatch):
    """Both `machines` and `hostnames` unset → ValueError (was: empty POST)."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="machines or hostnames"):
            await MachinesAcceptTool().run(maas_client, confirm=True)


async def test_machines_accept_empty_machines_no_call(monkeypatch):
    """Explicit empty `machines=[]` short-circuits: no MAAS call, returns []."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        result = await MachinesAcceptTool().run(maas_client, machines=[], confirm=True)
    assert result == []
    assert not mock.calls


async def test_machines_accept_by_hostnames(monkeypatch):
    """hostnames list resolves via one GET /machines/; resolved ids POSTed."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        mock.get("/api/2.0/machines/").mock(
            return_value=Response(
                200,
                json=[
                    {"system_id": "aa1", "hostname": "node-1"},
                    {"system_id": "bb2", "hostname": "node-2"},
                ],
            )
        )
        route = mock.post("/api/2.0/machines/?op=accept").mock(
            return_value=Response(200, json=[{"system_id": "aa1"}, {"system_id": "bb2"}])
        )
        async with maas_client:
            result = await MachinesAcceptTool().run(
                maas_client, hostnames=["node-1", "node-2"], confirm=True
            )
    assert route.call_count == 1
    body = route.calls.last.request.content.decode()
    assert "aa1" in body
    assert "bb2" in body
    assert result == [{"system_id": "aa1"}, {"system_id": "bb2"}]


async def test_machines_accept_unmatched_hostname_raises(monkeypatch):
    """accept is not per-host tolerant: any unmatched hostname raises
    ValueError naming the missing ones (does NOT silently accept a subset)."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        mock.get("/api/2.0/machines/").mock(
            return_value=Response(
                200,
                json=[{"system_id": "aa1", "hostname": "node-1"}],
            )
        )
        accept_route = mock.post("/api/2.0/machines/?op=accept").mock(
            return_value=Response(200, json=[])
        )
        async with maas_client:
            with pytest.raises(ValueError, match="ghost"):
                await MachinesAcceptTool().run(
                    maas_client, hostnames=["node-1", "ghost"], confirm=True
                )
    assert not accept_route.called


async def test_machines_accept_unmatched_hostname_raises_before_confirm(monkeypatch):
    """resolve_hostnames runs BEFORE the confirm gate (tree-wide rule from
    T4). confirm=False + an unresolvable hostname must surface the
    hostname-resolution error, not the confirm-gate error — addressing
    errors fail fast without waiting on the gate."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        mock.get("/api/2.0/machines/").mock(return_value=Response(200, json=[]))
        accept_route = mock.post("/api/2.0/machines/?op=accept").mock(
            return_value=Response(200, json=[])
        )
        async with maas_client:
            with pytest.raises(ValueError, match="ghost"):
                await MachinesAcceptTool().run(
                    maas_client, hostnames=["ghost"], confirm=False
                )
    assert not accept_route.called
