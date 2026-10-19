"""create_volume_group: POST /nodes/{system_id}/volume-groups/ with confirm gate."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.create_volume_group import CreateVolumeGroupTool
from maasmcp.maas.client import MaasClient
from maasmcp.maas.errors import MCPUpstreamError


@pytest.mark.asyncio
async def test_confirm_false_is_noop(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await CreateVolumeGroupTool().run(
                    maas_client,
                    system_id="abc",
                    name="vg0",
                    block_devices=[1, 2],
                    confirm=False,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_confirm_true_creates_volume_group(
    maas_client: MaasClient,
) -> None:
    vg = {"id": 1, "name": "vg0"}
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.post("/api/2.0/nodes/abc/volume-groups/").mock(
            return_value=Response(200, json=vg)
        )
        async with maas_client:
            result = await CreateVolumeGroupTool().run(
                maas_client,
                system_id="abc",
                name="vg0",
                block_devices=[1, 2],
                confirm=True,
            )
    assert route.call_count == 1
    assert result == vg


@pytest.mark.asyncio
async def test_empty_name_raises(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="name"):
                await CreateVolumeGroupTool().run(
                    maas_client,
                    system_id="abc",
                    name="",
                    block_devices=[1],
                    confirm=True,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_missing_members_raises(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="block device or partition"):
                await CreateVolumeGroupTool().run(
                    maas_client,
                    system_id="abc",
                    name="vg0",
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
                await CreateVolumeGroupTool().run(
                    maas_client,
                    system_id="",
                    name="vg0",
                    block_devices=[1],
                    confirm=True,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_create_volume_group_non_dict_response_raises(
    maas_client: MaasClient,
) -> None:
    """Schema drift: MAAS 200 with a non-dict body should not silently return {}."""
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.post("/api/2.0/nodes/abc/volume-groups/").mock(
            return_value=Response(200, json=["unexpected"])
        )
        async with maas_client:
            with pytest.raises(ValueError, match="non-dict"):
                await CreateVolumeGroupTool().run(
                    maas_client,
                    system_id="abc",
                    name="vg0",
                    block_devices=[1],
                    confirm=True,
                )
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_409_surfaces_as_upstream_error(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        mock.post("/api/2.0/nodes/abc/volume-groups/").mock(
            return_value=Response(409, text="machine not ready")
        )
        async with maas_client:
            with pytest.raises(MCPUpstreamError) as exc_info:
                await CreateVolumeGroupTool().run(
                    maas_client,
                    system_id="abc",
                    name="vg0",
                    block_devices=[1],
                    confirm=True,
                )
    # Body is stripped (security fix 5ad4a1a). Assert on status code only.
    assert "409" in str(exc_info.value)
