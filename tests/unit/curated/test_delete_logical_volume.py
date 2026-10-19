"""delete_logical_volume: POST /nodes/{system_id}/volume-group/{vg_id}/op-delete_logical_volume."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.delete_logical_volume import DeleteLogicalVolumeTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_confirm_false_is_noop(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await DeleteLogicalVolumeTool().run(
                    maas_client,
                    system_id="abc",
                    vg_id=1,
                    lv_id=2,
                    confirm=False,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_confirm_true_deletes_logical_volume(
    maas_client: MaasClient,
) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.post("/api/2.0/nodes/abc/volume-group/1/op-delete_logical_volume").mock(
            return_value=Response(204)
        )
        async with maas_client:
            result = await DeleteLogicalVolumeTool().run(
                maas_client,
                system_id="abc",
                vg_id=1,
                lv_id=2,
                confirm=True,
            )
    assert route.call_count == 1
    assert result is None or result == {}


@pytest.mark.asyncio
async def test_empty_system_id_with_confirm_true_still_fails(
    maas_client: MaasClient,
) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="system_id"):
                await DeleteLogicalVolumeTool().run(
                    maas_client,
                    system_id="",
                    vg_id=1,
                    lv_id=2,
                    confirm=True,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_vg_id_zero_raises(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="vg_id"):
                await DeleteLogicalVolumeTool().run(
                    maas_client,
                    system_id="abc",
                    vg_id=0,
                    lv_id=2,
                    confirm=True,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_lv_id_zero_raises(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="lv_id"):
                await DeleteLogicalVolumeTool().run(
                    maas_client,
                    system_id="abc",
                    vg_id=1,
                    lv_id=0,
                    confirm=True,
                )
    assert not mock.calls
