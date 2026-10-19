"""create_logical_volume: POST /nodes/{system_id}/volume-group/{vg_id}/op-create_logical_volume."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.create_logical_volume import CreateLogicalVolumeTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_confirm_false_is_noop(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await CreateLogicalVolumeTool().run(
                    maas_client,
                    system_id="abc",
                    vg_id=1,
                    name="lv0",
                    confirm=False,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_confirm_true_creates_logical_volume(
    maas_client: MaasClient,
) -> None:
    vg = {"id": 1, "name": "vg0", "logical_volumes": [{"name": "lv0"}]}
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.post("/api/2.0/nodes/abc/volume-group/1/op-create_logical_volume").mock(
            return_value=Response(200, json=vg)
        )
        async with maas_client:
            result = await CreateLogicalVolumeTool().run(
                maas_client,
                system_id="abc",
                vg_id=1,
                name="lv0",
                confirm=True,
            )
    assert route.call_count == 1
    assert result == vg


@pytest.mark.asyncio
async def test_empty_name_raises(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="name"):
                await CreateLogicalVolumeTool().run(
                    maas_client,
                    system_id="abc",
                    vg_id=1,
                    name="",
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
                await CreateLogicalVolumeTool().run(
                    maas_client,
                    system_id="",
                    vg_id=1,
                    name="lv0",
                    confirm=True,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_vg_id_zero_raises(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="vg_id"):
                await CreateLogicalVolumeTool().run(
                    maas_client,
                    system_id="abc",
                    vg_id=0,
                    name="lv0",
                    confirm=True,
                )
    assert not mock.calls
