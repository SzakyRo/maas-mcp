"""mount_block_device: op-mount with confirm gate."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.mount_block_device import MountBlockDeviceTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_confirm_false_is_noop(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await MountBlockDeviceTool().run(
                    maas_client,
                    system_id="abc",
                    block_device_id=11,
                    mount_point="/boot",
                    confirm=False,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_confirm_true_mounts_block_device(maas_client: MaasClient) -> None:
    """Block-device mount uses path-suffix op-mount (not ?op=mount, which is
    partition-only — see memory maas-partition-ops-query-param)."""
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.post("/api/2.0/nodes/abc/blockdevices/11/op-mount").mock(
            return_value=Response(200, json={})
        )
        async with maas_client:
            result = await MountBlockDeviceTool().run(
                maas_client,
                system_id="abc",
                block_device_id=11,
                mount_point="/boot",
                confirm=True,
            )
    assert route.call_count == 1
    assert result["status"] == "ok"
    assert result["operation"] == "mount"


@pytest.mark.asyncio
async def test_mount_point_must_be_absolute(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="mount_point"):
                await MountBlockDeviceTool().run(
                    maas_client,
                    system_id="abc",
                    block_device_id=11,
                    mount_point="boot",
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
                await MountBlockDeviceTool().run(
                    maas_client,
                    system_id="",
                    block_device_id=11,
                    mount_point="/boot",
                    confirm=True,
                )
    assert not mock.calls
