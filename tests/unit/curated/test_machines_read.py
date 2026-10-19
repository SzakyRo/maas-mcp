"""machines_read: GET /machines/ (raw read with filters)."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.machines_read import MachinesReadTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_single_page_no_filters(maas_client: MaasClient) -> None:
    payload = [{"system_id": "abc", "hostname": "h-abc"}]
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.get("/api/2.0/machines/").mock(return_value=Response(200, json=payload))
        async with maas_client:
            result = await MachinesReadTool().run(maas_client)
    assert route.call_count == 1
    assert result == payload
    url = route.calls.last.request.url
    assert url.path.endswith("/api/2.0/machines/")
    # No filters set and the internal paginate flag must not go over the wire.
    assert url.query == b""


@pytest.mark.asyncio
async def test_zone_filter_passes_query_param(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.get("/api/2.0/machines/").mock(
            return_value=Response(200, json=[{"system_id": "a"}])
        )
        async with maas_client:
            result = await MachinesReadTool().run(maas_client, zone="zone-1", cpu_count=8)
    assert result == [{"system_id": "a"}]
    params = route.calls.last.request.url.params
    assert params["zone"] == "zone-1"
    assert params["cpu_count"] == "8"
    assert "paginate" not in params
    assert "hostname" not in params
