"""machines_list_allocated: GET /machines/?op=list_allocated."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.machines_list_allocated import MachinesListAllocatedTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_single_page_lists_allocated(maas_client: MaasClient) -> None:
    payload = [
        {"system_id": "abc", "hostname": "h-abc", "status_name": "ALLOCATED"},
        {"system_id": "def", "hostname": "h-def", "status_name": "ALLOCATED"},
    ]
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.get("/api/2.0/machines/").mock(return_value=Response(200, json=payload))
        async with maas_client:
            result = await MachinesListAllocatedTool().run(maas_client)
    assert route.call_count == 1
    assert result == payload
    url = route.calls.last.request.url
    assert url.path.endswith("/api/2.0/machines/")
    assert url.params["op"] == "list_allocated"
    # The internal paginate flag must never go over the wire.
    assert "paginate" not in url.params
