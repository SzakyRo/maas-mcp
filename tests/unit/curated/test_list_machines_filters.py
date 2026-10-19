"""list_machines: new server-side and client-side filter kwargs."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.list_machines import ListMachinesTool
from maasmcp.maas.client import MaasClient


def _machine(system_id: str, **kw: object) -> dict[str, object]:
    base: dict[str, object] = {
        "system_id": system_id,
        "hostname": f"h-{system_id}",
        "status_name": "READY",
        "power_state": "on",
        "tag_names": [],
        "pool": {"name": "default"},
        "zone": {"name": "zone-1"},
        "cpu_count": 4,
        "memory": 8192,
    }
    base.update(kw)
    return base


@pytest.mark.asyncio
async def test_zone_filter_passes_query_param(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.get("/api/2.0/machines/").mock(
            return_value=Response(200, json=[_machine("a"), _machine("b")])
        )
        async with maas_client:
            result = await ListMachinesTool().run(maas_client, zone="zone-1")
    assert "zone=zone-1" in str(route.calls.last.request.url)
    assert len(result) == 2


@pytest.mark.asyncio
async def test_cpu_count_min_passes_server_side_query_param(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.get("/api/2.0/machines/").mock(
            return_value=Response(200, json=[_machine("big", cpu_count=16)])
        )
        async with maas_client:
            result = await ListMachinesTool().run(maas_client, cpu_count_min=8)
    assert "cpu_count=8" in str(route.calls.last.request.url)
    assert len(result) == 1


@pytest.mark.asyncio
async def test_memory_min_passes_server_side_query_param(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.get("/api/2.0/machines/").mock(
            return_value=Response(200, json=[_machine("high", memory=32768)])
        )
        async with maas_client:
            result = await ListMachinesTool().run(maas_client, memory_min=16384)
    assert "mem=16384" in str(route.calls.last.request.url)
    assert len(result) == 1


@pytest.mark.asyncio
async def test_combined_filters_pass_query_params(maas_client: MaasClient) -> None:
    """All three filters AND together in the MAAS request URL."""
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.get("/api/2.0/machines/").mock(
            return_value=Response(200, json=[_machine("a")])
        )
        async with maas_client:
            await ListMachinesTool().run(
                maas_client, zone="zone-1", cpu_count_min=8, memory_min=16384
            )
    url = str(route.calls.last.request.url)
    assert "zone=zone-1" in url
    assert "cpu_count=8" in url
    assert "mem=16384" in url


@pytest.mark.asyncio
async def test_no_kwargs_unchanged_behaviour(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        mock.get("/api/2.0/machines/").mock(return_value=Response(200, json=[_machine("a")]))
        async with maas_client:
            result = await ListMachinesTool().run(maas_client)
    assert len(result) == 1
