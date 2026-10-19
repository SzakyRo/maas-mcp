"""machine_details: GET /machines/{system_id}/?op=details (read-only)."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.machine_details import MachineDetailsTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_single_page_returns_details(maas_client: MaasClient) -> None:
    payload = {"system_id": "abc", "hostname": "h-abc"}
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.get("/api/2.0/machines/abc/").mock(return_value=Response(200, json=payload))
        async with maas_client:
            result = await MachineDetailsTool().run(maas_client, system_id="abc")
    assert route.call_count == 1
    assert result == payload
    url = route.calls.last.request.url
    assert url.path.endswith("/api/2.0/machines/abc/")
    assert url.params["op"] == "details"
    # The internal paginate flag must never go over the wire.
    assert "paginate" not in url.params
