import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated._resolve import resolve_hostnames, resolve_system_id
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


def _client(monkeypatch) -> MaasClient:
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    c = MaasClient(cfg.maas)
    c.base_url = cfg.maas.base_url
    return c


async def test_neither_raises(monkeypatch):
    c = _client(monkeypatch)
    async with c:
        with pytest.raises(ValueError, match="at least one of system_id or hostname"):
            await resolve_system_id(c, None, None)


async def test_system_id_only_no_http(monkeypatch):
    """system_id-only resolution MUST NOT touch the network."""
    c = _client(monkeypatch)
    with respx.mock(base_url=c.base_url, assert_all_called=False) as mock:
        route = mock.get("/api/2.0/machines/").mock(return_value=Response(200, json=[]))
        async with c:
            assert await resolve_system_id(c, "abc123", None) == "abc123"
    assert not route.called


async def test_hostname_hit(monkeypatch):
    c = _client(monkeypatch)
    with respx.mock(base_url=c.base_url, assert_all_called=False) as mock:
        route = mock.get("/api/2.0/machines/", params={"hostname": "node-1"}).mock(
            return_value=Response(200, json=[{"system_id": "xy7zab", "hostname": "node-1"}])
        )
        async with c:
            assert await resolve_system_id(c, None, "node-1") == "xy7zab"
    assert route.called


async def test_hostname_miss(monkeypatch):
    c = _client(monkeypatch)
    with respx.mock(base_url=c.base_url, assert_all_called=False) as mock:
        mock.get("/api/2.0/machines/").mock(return_value=Response(200, json=[]))
        async with c:
            with pytest.raises(ValueError, match="no machine found with hostname"):
                await resolve_system_id(c, None, "ghost")


async def test_both_matching(monkeypatch):
    c = _client(monkeypatch)
    with respx.mock(base_url=c.base_url, assert_all_called=False) as mock:
        mock.get("/api/2.0/machines/", params={"hostname": "node-1"}).mock(
            return_value=Response(200, json=[{"system_id": "xy7zab"}])
        )
        async with c:
            assert await resolve_system_id(c, "xy7zab", "node-1") == "xy7zab"


async def test_both_conflicting(monkeypatch):
    c = _client(monkeypatch)
    with respx.mock(base_url=c.base_url, assert_all_called=False) as mock:
        mock.get("/api/2.0/machines/", params={"hostname": "node-1"}).mock(
            return_value=Response(200, json=[{"system_id": "xy7zab"}])
        )
        async with c:
            with pytest.raises(ValueError, match="does not belong to hostname"):
                await resolve_system_id(c, "other9", "node-1")


async def test_machine_list_handles_results_dict(monkeypatch):
    """The fleet-map fetch routes through paginated_get(paginate=True) so a
    paginated MAAS doesn't drop later pages. A single-page list response is
    the realistic shape (list envelopes, not dict envelopes, for the
    auto-paginated list endpoint)."""
    c = _client(monkeypatch)
    with respx.mock(base_url=c.base_url, assert_all_called=False) as mock:
        mock.get("/api/2.0/machines/", params={"limit": "200", "offset": "0"}).mock(
            return_value=Response(200, json=[{"system_id": "s1", "hostname": "h1"}])
        )
        async with c:
            mapping, missing = await resolve_hostnames(c, ["h1", "h2"])
    assert mapping == {"h1": "s1"}
    assert missing == ["h2"]


async def test_resolve_hostnames_uses_paginated_get(monkeypatch):
    """Fleet-map fetch must use paginated_get(paginate=True), not a single
    unpaginated GET, so deployments that actually paginate /machines/ don't
    drop later pages."""
    c = _client(monkeypatch)
    with respx.mock(base_url=c.base_url, assert_all_called=False) as mock:
        # Match the first paginated page (limit=200, offset=0); paginated_get
        # walks further pages on its own. Returning a short page signals end.
        route = mock.get(
            "/api/2.0/machines/", params={"limit": "200", "offset": "0"}
        ).mock(return_value=Response(200, json=[{"system_id": "s1", "hostname": "h1"}]))
        async with c:
            await resolve_hostnames(c, ["h1"])
    assert route.called


async def test_resolve_hostnames_empty(monkeypatch):
    c = _client(monkeypatch)
    async with c:
        assert await resolve_hostnames(c, []) == ({}, [])
