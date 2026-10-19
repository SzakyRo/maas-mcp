"""mount_partition: op-mount with confirm gate."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.mount_partition import MountPartitionTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_confirm_false_is_noop(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await MountPartitionTool().run(
                    maas_client,
                    system_id="abc",
                    block_device_id=1,
                    partition_id=5,
                    mount_point="/mnt/data",
                    confirm=False,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_confirm_true_mounts_partition(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.post("/api/2.0/nodes/abc/blockdevices/1/partitions/5?op=mount").mock(
            return_value=Response(200, json={})
        )
        async with maas_client:
            result = await MountPartitionTool().run(
                maas_client,
                system_id="abc",
                block_device_id=1,
                partition_id=5,
                mount_point="/mnt/data",
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
                await MountPartitionTool().run(
                    maas_client,
                    system_id="abc",
                    block_device_id=1,
                    partition_id=5,
                    mount_point="mnt/data",
                    confirm=True,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_empty_system_id_with_confirm_true_still_fails(
    maas_client: MaasClient,
) -> None:
    """Path validation must happen BEFORE the confirm check."""
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="system_id"):
                await MountPartitionTool().run(
                    maas_client,
                    system_id="",
                    block_device_id=1,
                    partition_id=5,
                    mount_point="/mnt/data",
                    confirm=True,
                )
    assert not mock.calls
