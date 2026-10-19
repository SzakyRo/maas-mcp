"""bulk_untag_machines: asyncio.gather fan-out, remove= body field."""

from __future__ import annotations

import asyncio

import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated._fanout import _FANOUT_CONCURRENCY
from maasmcp.curated.bulk_untag_machines import BulkUntagMachinesTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_happy_path_sends_remove_field(maas_client: MaasClient) -> None:
    """Each POST body contains 'remove=<sid>' and no 'add'."""
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.post("/api/2.0/tags/x/op-update_nodes").mock(
            return_value=Response(200, json=[])
        )
        async with maas_client:
            result = await BulkUntagMachinesTool().run(
                maas_client, system_ids=["a", "b"], tag="x", confirm=True
            )
    assert route.call_count == 2
    for call in route.calls:
        body = call.request.content.decode()
        assert 'name="remove"' in body
        assert 'name="add"' not in body
    assert all(r["status"] == "ok" for r in result)


@pytest.mark.asyncio
async def test_partial_failure_per_item(maas_client: MaasClient) -> None:
    ids = ["ok", "fail"]

    def side_effect(request):
        body = request.content.decode()
        if 'name="remove"\r\n\r\nfail' in body:
            return Response(404, text="tag not found")
        return Response(200, json=[])

    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        mock.post("/api/2.0/tags/x/op-update_nodes").mock(side_effect=side_effect)
        async with maas_client:
            result = await BulkUntagMachinesTool().run(
                maas_client, system_ids=ids, tag="x", confirm=True
            )
    assert result[0]["status"] == "ok"
    assert result[1]["status"] == "error"
    # Commit 5ad4a1a strips response bodies from MCPUpstreamError; assert on
    # status code only, not the body text.
    assert "404" in result[1]["error"]


@pytest.mark.asyncio
async def test_empty_inputs(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        result = await BulkUntagMachinesTool().run(maas_client, system_ids=[], tag="x")
    assert result == []
    assert not mock.calls


@pytest.mark.asyncio
async def test_empty_tag_raises(maas_client: MaasClient) -> None:
    with pytest.raises(ValueError, match="tag"):
        await BulkUntagMachinesTool().run(maas_client, system_ids=["a"], tag="", confirm=True)


@pytest.mark.asyncio
async def test_requires_confirm(maas_client: MaasClient) -> None:
    """confirm=False (or omitted) raises before any HTTP call."""
    with (
        respx.mock(base_url=maas_client.base_url) as mock,  # type: ignore[attr-defined]
        pytest.raises(ValueError, match="confirm=True"),
    ):
        await BulkUntagMachinesTool().run(maas_client, system_ids=["a"], tag="x")
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
            await BulkUntagMachinesTool().run(maas_client, system_ids=ids, tag="x", confirm=True)
    assert peak <= _FANOUT_CONCURRENCY
    assert _FANOUT_CONCURRENCY == 10


async def test_bulk_untag_by_hostnames(monkeypatch) -> None:
    """hostnames list resolves via one fleet fetch; unmatched → error entry."""
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
        tag_route = mock.post("/api/2.0/tags/prod/op-update_nodes").mock(
            return_value=Response(200, json={})
        )
        async with maas_client:
            results = await BulkUntagMachinesTool().run(
                maas_client,
                hostnames=["node-1", "ghost"],
                tag="prod",
                confirm=True,
            )
    assert tag_route.call_count == 1
    by_sid = {r["system_id"]: r for r in results}
    assert by_sid["aa1"]["status"] == "ok"
    assert by_sid["ghost"]["status"] == "error"


async def test_bulk_untag_both_none_raises(monkeypatch) -> None:
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="system_ids or hostnames"):
            await BulkUntagMachinesTool().run(maas_client, tag="x", confirm=True)


@pytest.mark.asyncio
async def test_invalid_system_id_validates_before_confirm_gate(
    maas_client: MaasClient,
) -> None:
    """Validation must fire BEFORE the confirm gate so an invalid explicit
    system_id surfaces the validation error rather than the generic
    confirm-gate rejection."""
    with (
        respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock,  # type: ignore[attr-defined]
        pytest.raises(ValueError, match="system_id must be 1-64"),
    ):
        await BulkUntagMachinesTool().run(
            maas_client, system_ids=["../bad"], tag="x", confirm=False
        )
    assert not mock.calls
