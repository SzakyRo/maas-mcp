"""bulk_tag_machines: asyncio.gather fan-out, partial-failure semantics."""

from __future__ import annotations

import asyncio

import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated._fanout import _FANOUT_CONCURRENCY
from maasmcp.curated.bulk_tag_machines import BulkTagMachinesTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_happy_path_issues_one_post_per_host(maas_client: MaasClient) -> None:
    """Fan-out: N POSTs in parallel, one per system_id."""
    ids = ["a", "b", "c"]
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.post("/api/2.0/tags/k8s/op-update_nodes").mock(
            return_value=Response(200, json=[])
        )
        async with maas_client:
            result = await BulkTagMachinesTool().run(
                maas_client, system_ids=ids, tag="k8s", confirm=True
            )
    assert route.call_count == len(ids)
    assert [r["system_id"] for r in result] == ids
    assert all(r["status"] == "ok" for r in result)


@pytest.mark.asyncio
async def test_partial_failure_preserves_order(maas_client: MaasClient) -> None:
    """One host 403s, the rest succeed — result keeps input order."""
    ids = ["ok1", "fail", "ok2"]

    def side_effect(request):
        body = request.content.decode()
        if "fail" in body:
            return Response(403, text="forbidden")
        return Response(200, json=[])

    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        mock.post("/api/2.0/tags/x/op-update_nodes").mock(side_effect=side_effect)
        async with maas_client:
            result = await BulkTagMachinesTool().run(
                maas_client, system_ids=ids, tag="x", confirm=True
            )
    assert [r["system_id"] for r in result] == ids
    assert result[0]["status"] == "ok"
    assert result[1]["status"] == "error"
    # Commit 5ad4a1a strips response bodies from MCPUpstreamError; assert
    # on the status code ("upstream 403") only, not the body text.
    assert "403" in result[1]["error"]
    assert result[2]["status"] == "ok"


@pytest.mark.asyncio
async def test_empty_system_ids_is_noop(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        result = await BulkTagMachinesTool().run(maas_client, system_ids=[], tag="x")
    assert result == []
    assert not mock.calls


@pytest.mark.asyncio
async def test_fanout_semaphore_caps_concurrency(maas_client: MaasClient) -> None:
    """With 25 hosts and cap 10, never more than 10 concurrent in-flight POSTs."""
    in_flight = 0
    peak = 0

    async def side_effect(request):  # type: ignore[no-untyped-def]
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.05)
        in_flight -= 1
        return Response(200, json=[])

    ids = [f"m{i}" for i in range(25)]
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        mock.post("/api/2.0/tags/x/op-update_nodes").mock(side_effect=side_effect)
        async with maas_client:
            await BulkTagMachinesTool().run(maas_client, system_ids=ids, tag="x", confirm=True)
    assert peak <= _FANOUT_CONCURRENCY
    assert _FANOUT_CONCURRENCY == 10


@pytest.mark.asyncio
async def test_empty_tag_raises_value_error(maas_client: MaasClient) -> None:
    with pytest.raises(ValueError, match="tag"):
        await BulkTagMachinesTool().run(maas_client, system_ids=["a"], tag="", confirm=True)


@pytest.mark.asyncio
async def test_requires_confirm(maas_client: MaasClient) -> None:
    """confirm=False (or omitted) raises before any HTTP call."""
    with (
        respx.mock(base_url=maas_client.base_url) as mock,  # type: ignore[attr-defined]
        pytest.raises(ValueError, match="confirm=True"),
    ):
        await BulkTagMachinesTool().run(maas_client, system_ids=["a"], tag="x")
    assert not mock.calls


async def test_bulk_tag_by_hostnames(monkeypatch) -> None:
    """hostnames list triggers one fleet fetch, fans out to resolved sids;
    unmatched hostnames become per-host error entries (BulkTagResult tolerates
    the raw hostname string in the system_id field)."""
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
        tag_route = mock.post("/api/2.0/tags/prod/op-update_nodes").mock(
            return_value=Response(200, json={})
        )
        async with maas_client:
            results = await BulkTagMachinesTool().run(
                maas_client,
                hostnames=["node-1", "node-2", "ghost"],
                tag="prod",
                confirm=True,
            )
    assert tag_route.call_count == 2  # only resolved hosts fan out
    assert {r["system_id"] for r in results} == {"aa1", "bb2", "ghost"}
    ghost = next(r for r in results if r["system_id"] == "ghost")
    assert ghost["status"] == "error"
    assert "ghost" in ghost["error"]


async def test_bulk_tag_system_ids_and_hostnames_union(monkeypatch) -> None:
    """Both params provided → system_ids pass through, hostnames resolve,
    union is fanned out."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        mock.get("/api/2.0/machines/").mock(
            return_value=Response(200, json=[{"system_id": "hh1", "hostname": "h-only"}])
        )
        mock.post("/api/2.0/tags/u/op-update_nodes").mock(return_value=Response(200, json={}))
        async with maas_client:
            results = await BulkTagMachinesTool().run(
                maas_client,
                system_ids=["sid-direct"],
                hostnames=["h-only"],
                tag="u",
                confirm=True,
            )
    by_sid = {r["system_id"] for r in results}
    assert by_sid == {"sid-direct", "hh1"}


async def test_bulk_tag_both_none_raises(monkeypatch) -> None:
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="system_ids or hostnames"):
            await BulkTagMachinesTool().run(maas_client, tag="x", confirm=True)


async def test_bulk_tag_empty_hostnames_is_noop(monkeypatch) -> None:
    """Explicit empty hostnames (with non-empty system_ids) keeps old behavior."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:
        result = await BulkTagMachinesTool().run(
            maas_client, hostnames=[], tag="x", confirm=True
        )
    assert result == []
    assert not mock.calls


@pytest.mark.asyncio
async def test_invalid_system_id_validates_before_confirm_gate(maas_client: MaasClient) -> None:
    """Validation must fire BEFORE the confirm gate so an invalid explicit
    system_id surfaces the validation error rather than the generic
    confirm-gate rejection."""
    with (
        respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock,  # type: ignore[attr-defined]
        pytest.raises(ValueError, match="system_id must be 1-64"),
    ):
        await BulkTagMachinesTool().run(
            maas_client, system_ids=["../bad"], tag="x", confirm=False
        )
    assert not mock.calls


@pytest.mark.asyncio
async def test_confirm_message_includes_actual_ids(maas_client: MaasClient) -> None:
    """Gate message lists the actual system_ids (and hostnames), not counts."""
    with pytest.raises(ValueError, match=r"system_ids=\['abc', 'def'\]"):
        await BulkTagMachinesTool().run(
            maas_client, system_ids=["abc", "def"], tag="x", confirm=False
        )
