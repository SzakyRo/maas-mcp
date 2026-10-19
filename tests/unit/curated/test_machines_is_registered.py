"""machines_is_registered: GET /machines/?op=is_registered."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.machines_is_registered import MachinesIsRegisteredTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_registered_mac_returns_true(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.get("/api/2.0/machines/").mock(return_value=Response(200, json=True))
        async with maas_client:
            result = await MachinesIsRegisteredTool().run(
                maas_client, mac_address="01:02:03:04:05:06"
            )
    assert route.call_count == 1
    assert result is True
    url = route.calls.last.request.url
    assert url.params["op"] == "is_registered"
    assert url.params["mac_address"] == "01:02:03:04:05:06"


@pytest.mark.asyncio
async def test_unregistered_mac_returns_false(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        mock.get("/api/2.0/machines/").mock(return_value=Response(200, json=False))
        async with maas_client:
            result = await MachinesIsRegisteredTool().run(
                maas_client, mac_address="aa:bb:cc:dd:ee:ff"
            )
    assert result is False
