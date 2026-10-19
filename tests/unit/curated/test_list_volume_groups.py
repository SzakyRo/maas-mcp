"""list_volume_groups: GET /nodes/{system_id}/volume-groups/."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.list_volume_groups import ListVolumeGroupsTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_list_volume_groups_returns_list(maas_client: MaasClient) -> None:
    vgs = [{"id": 1, "name": "vg0"}]
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.get("/api/2.0/nodes/abc/volume-groups/").mock(
            return_value=Response(200, json=vgs)
        )
        async with maas_client:
            result = await ListVolumeGroupsTool().run(maas_client, system_id="abc")
    assert route.call_count == 1
    assert result == vgs


@pytest.mark.asyncio
async def test_empty_system_id_raises_value_error(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="system_id"):
                await ListVolumeGroupsTool().run(maas_client, system_id="")
    assert not mock.calls
