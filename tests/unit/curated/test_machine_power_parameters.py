"""machine_power_parameters: GET /machines/{system_id}/?op=power_parameters."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.machine_power_parameters import MachinePowerParametersTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_single_page_returns_power_parameters(maas_client: MaasClient) -> None:
    payload = {"power_type": "ipmi", "power_address": "10.0.0.2"}
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.get("/api/2.0/machines/abc/").mock(return_value=Response(200, json=payload))
        async with maas_client:
            result = await MachinePowerParametersTool().run(maas_client, system_id="abc")
    assert route.call_count == 1
    assert result == payload
    url = route.calls.last.request.url
    assert url.params["op"] == "power_parameters"
