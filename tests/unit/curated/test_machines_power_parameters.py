"""machines_power_parameters: GET /machines/?op=power_parameters."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.machines_power_parameters import MachinesPowerParametersTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_single_page_sends_id_and_op(maas_client: MaasClient) -> None:
    payload = [{"system_id": "abc", "power_type": "ipmi"}]
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.get("/api/2.0/machines/").mock(return_value=Response(200, json=payload))
        async with maas_client:
            result = await MachinesPowerParametersTool().run(maas_client, id="abc")
    assert route.call_count == 1
    assert result == payload
    url = route.calls.last.request.url
    assert url.params["op"] == "power_parameters"
    assert url.params["id"] == "abc"
    # The internal paginate flag must never go over the wire.
    assert "paginate" not in url.params
