"""bulk_power_control_machines: per-id op-power_* POSTs in parallel."""

from __future__ import annotations

import asyncio

import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated._fanout import _FANOUT_CONCURRENCY
from maasmcp.curated.bulk_power_control_machines import BulkPowerControlMachinesTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_on_action_hits_power_on_per_id(maas_client: MaasClient) -> None:
    ids = ["a", "b"]
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        mock.post("/api/2.0/machines/a/op-power_on").mock(return_value=Response(200, json={}))
        mock.post("/api/2.0/machines/b/op-power_on").mock(return_value=Response(200, json={}))
        async with maas_client:
            result = await BulkPowerControlMachinesTool().run(
                maas_client, system_ids=ids, action="on", confirm=True
            )
    assert all(r["status"] == "ok" for r in result)
    assert [r["system_id"] for r in result] == ids


@pytest.mark.asyncio
async def test_cycle_action_synthesizes_off_then_on(maas_client: MaasClient) -> None:
    """MAAS has no op-power_cycle; cycle is off + pause + on per host."""
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        # busy-status pre-check (returns Ready, so cycle proceeds)
        mock.get("/api/2.0/machines/x/").mock(
            return_value=Response(200, json={"status_name": "Ready"})
        )
        off_route = mock.post("/api/2.0/machines/x/op-power_off").mock(
            return_value=Response(204, json=None)
        )
        on_route = mock.post("/api/2.0/machines/x/op-power_on").mock(
            return_value=Response(204, json=None)
        )
        async with maas_client:
            await BulkPowerControlMachinesTool().run(
                maas_client, system_ids=["x"], action="cycle", confirm=True
            )
    assert off_route.called
    assert on_route.called


@pytest.mark.asyncio
async def test_off_action_hits_power_off(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        # busy-status pre-check (returns Ready, so off proceeds)
        mock.get("/api/2.0/machines/x/").mock(
            return_value=Response(200, json={"status_name": "Ready"})
        )
        route = mock.post("/api/2.0/machines/x/op-power_off").mock(
            return_value=Response(200, json={})
        )
        async with maas_client:
            await BulkPowerControlMachinesTool().run(
                maas_client, system_ids=["x"], action="off", confirm=True
            )
    assert route.called


@pytest.mark.asyncio
async def test_invalid_action_raises_value_error(maas_client: MaasClient) -> None:
    """Invalid action raises BEFORE confirm check."""
    with pytest.raises(ValueError, match="action"):
        await BulkPowerControlMachinesTool().run(
            maas_client, system_ids=["x"], action="reboot", confirm=True
        )


@pytest.mark.asyncio
async def test_partial_failure(maas_client: MaasClient) -> None:
    def side_effect(request):
        if "fail" in str(request.url):
            return Response(403, text="forbidden")
        return Response(200, json={})

    ids = ["ok", "fail"]
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        for sid in ids:
            mock.post(f"/api/2.0/machines/{sid}/op-power_on").mock(side_effect=side_effect)
        async with maas_client:
            result = await BulkPowerControlMachinesTool().run(
                maas_client, system_ids=ids, action="on", confirm=True
            )
    assert result[0]["status"] == "ok"
    assert result[1]["status"] == "error"


@pytest.mark.asyncio
async def test_empty_system_ids_is_noop(maas_client: MaasClient) -> None:
    """Empty input short-circuits before confirm check, no MAAS call."""
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:  # type: ignore[attr-defined]
        result = await BulkPowerControlMachinesTool().run(maas_client, system_ids=[], action="on")
    assert result == []
    assert not mock.calls


@pytest.mark.asyncio
async def test_requires_confirm(maas_client: MaasClient) -> None:
    """Gate runs before any MAAS call. confirm=False (default) must reject."""
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:  # type: ignore[attr-defined]
        route = mock.post("/api/2.0/machines/x/op-power_off").mock(
            return_value=Response(200, json={})
        )
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await BulkPowerControlMachinesTool().run(
                    maas_client, system_ids=["x"], action="off"
                )
    assert route.call_count == 0


@pytest.mark.asyncio
async def test_off_skips_busy_status(maas_client: MaasClient) -> None:
    """For off/cycle, hosts in Deploying/Commissioning status are skipped
    with a per-host error (mirrors single-machine power_control._BUSY_STATUSES)."""
    with respx.mock(base_url=maas_client.base_url, assert_all_called=False) as mock:  # type: ignore[attr-defined]
        # busy host
        mock.get("/api/2.0/machines/busy/").mock(
            return_value=Response(200, json={"status_name": "Deploying"})
        )
        # idle host
        mock.get("/api/2.0/machines/ok/").mock(
            return_value=Response(200, json={"status_name": "Ready"})
        )
        ok_route = mock.post("/api/2.0/machines/ok/op-power_off").mock(
            return_value=Response(200, json={})
        )
        busy_route = mock.post("/api/2.0/machines/busy/op-power_off").mock(
            return_value=Response(200, json={})
        )
        async with maas_client:
            result = await BulkPowerControlMachinesTool().run(
                maas_client, system_ids=["busy", "ok"], action="off", confirm=True
            )
    assert ok_route.called
    assert not busy_route.called
    by_sid = {item["system_id"]: item for item in result}
    assert by_sid["busy"]["status"] == "error"
    assert "Deploying" in by_sid["busy"]["error"]
    assert by_sid["ok"]["status"] == "ok"


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
        return Response(200, json={})

    ids = [f"m{i}" for i in range(25)]
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        for sid in ids:
            mock.post(f"/api/2.0/machines/{sid}/op-power_on").mock(side_effect=side_effect)
        async with maas_client:
            await BulkPowerControlMachinesTool().run(
                maas_client, system_ids=ids, action="on", confirm=True
            )
    assert peak <= _FANOUT_CONCURRENCY
    assert _FANOUT_CONCURRENCY == 10


async def test_bulk_power_control_by_hostnames(monkeypatch) -> None:
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
        on_route = mock.post("/api/2.0/machines/aa1/op-power_on").mock(
            return_value=Response(200, json={})
        )
        async with maas_client:
            results = await BulkPowerControlMachinesTool().run(
                maas_client,
                hostnames=["node-1", "ghost"],
                action="on",
                confirm=True,
            )
    assert on_route.call_count == 1
    by_sid = {r["system_id"]: r for r in results}
    assert by_sid["aa1"]["status"] == "ok"
    assert by_sid["ghost"]["status"] == "error"


async def test_bulk_power_control_both_none_raises(monkeypatch) -> None:
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="system_ids or hostnames"):
            await BulkPowerControlMachinesTool().run(
                maas_client, action="on", confirm=True
            )


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
        await BulkPowerControlMachinesTool().run(
            maas_client, system_ids=["../bad"], action="on", confirm=False
        )
    assert not mock.calls
