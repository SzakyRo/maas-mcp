"""get_volume_group: GET /nodes/{system_id}/volume-group/{id}/."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.get_volume_group import GetVolumeGroupTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_get_volume_group_returns_dict(maas_client: MaasClient) -> None:
    vg = {"id": 3, "name": "vg0"}
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.get("/api/2.0/nodes/abc/volume-group/3/").mock(
            return_value=Response(200, json=vg)
        )
        async with maas_client:
            result = await GetVolumeGroupTool().run(maas_client, system_id="abc", vg_id=3)
    assert route.call_count == 1
    assert result == vg


@pytest.mark.asyncio
async def test_empty_system_id_raises_value_error(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="system_id"):
                await GetVolumeGroupTool().run(maas_client, system_id="", vg_id=1)
    assert not mock.calls


@pytest.mark.asyncio
async def test_vg_id_zero_raises_value_error(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="vg_id"):
                await GetVolumeGroupTool().run(maas_client, system_id="abc", vg_id=0)
    assert not mock.calls


@pytest.mark.asyncio
async def test_get_volume_group_non_dict_response_raises(
    maas_client: MaasClient,
) -> None:
    """Schema drift: MAAS 200 with a non-dict body should not silently return {}."""
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.get("/api/2.0/nodes/abc/volume-group/3/").mock(
            return_value=Response(200, json=["unexpected"])
        )
        async with maas_client:
            with pytest.raises(ValueError, match="non-dict"):
                await GetVolumeGroupTool().run(maas_client, system_id="abc", vg_id=3)
    assert route.call_count == 1
