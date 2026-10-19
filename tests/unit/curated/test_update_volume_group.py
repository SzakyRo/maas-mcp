"""update_volume_group: PUT /nodes/{system_id}/volume-group/{id}/ with confirm gate."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.update_volume_group import UpdateVolumeGroupTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_confirm_false_is_noop(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await UpdateVolumeGroupTool().run(
                    maas_client,
                    system_id="abc",
                    vg_id=1,
                    name="vg0-renamed",
                    confirm=False,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_confirm_true_updates_volume_group(
    maas_client: MaasClient,
) -> None:
    vg = {"id": 1, "name": "vg0-renamed"}
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.put("/api/2.0/nodes/abc/volume-group/1/").mock(
            return_value=Response(200, json=vg)
        )
        async with maas_client:
            result = await UpdateVolumeGroupTool().run(
                maas_client,
                system_id="abc",
                vg_id=1,
                name="vg0-renamed",
                confirm=True,
            )
    assert route.call_count == 1
    assert result == vg


@pytest.mark.asyncio
async def test_no_update_fields_raises_without_put(maas_client: MaasClient) -> None:
    """All optional args None must fail fast (no empty-body PUT), as with
    update_vlan/update_interface."""
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="nothing to update"):
                await UpdateVolumeGroupTool().run(
                    maas_client,
                    system_id="abc",
                    vg_id=1,
                    confirm=True,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_empty_system_id_with_confirm_true_still_fails(
    maas_client: MaasClient,
) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="system_id"):
                await UpdateVolumeGroupTool().run(
                    maas_client,
                    system_id="",
                    vg_id=1,
                    name="vg0",
                    confirm=True,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_vg_id_zero_raises(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="vg_id"):
                await UpdateVolumeGroupTool().run(
                    maas_client,
                    system_id="abc",
                    vg_id=0,
                    confirm=True,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_update_volume_group_non_dict_response_raises(
    maas_client: MaasClient,
) -> None:
    """Schema drift: MAAS 200 with a non-dict body should not silently return {}."""
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.put("/api/2.0/nodes/abc/volume-group/1/").mock(
            return_value=Response(200, json=["unexpected"])
        )
        async with maas_client:
            with pytest.raises(ValueError, match="non-dict"):
                await UpdateVolumeGroupTool().run(
                    maas_client,
                    system_id="abc",
                    vg_id=1,
                    name="vg0",
                    confirm=True,
                )
    assert route.call_count == 1
