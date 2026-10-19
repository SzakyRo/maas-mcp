"""unmount_block_device: POST /nodes/{system_id}/blockdevices/{id}/op-unmount.

Mirror of :class:`UnmountPartitionTool` for whole block devices (RAIDs, VGs).
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.storage import StatusOperation
from maasmcp.curated._storage_paths import _validate_ids, unmount_block_device_path
from maasmcp.maas.client import MaasClient


class UnmountBlockDeviceTool:
    name = "unmount_block_device"
    description = (
        "Unmount a mounted filesystem on a whole block device (RAID, volume "
        "group, or raw disk). Use this before reformatting or reconfiguring the "
        "device; for partitions, use unmount_partition instead. Verify the "
        "target with list_block_devices or storage_summary first. "
        "Returns {'status': 'ok', 'system_id', 'resource_id', 'operation': 'unmount'}. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        block_device_id: Annotated[int, Field(description="ID of the block device to unmount.")],
        *,
        system_id: Annotated[
            str | None,
            Field(
                description="MAAS system_id of the machine. "
                "Provide this or hostname, exactly one."
            ),
        ] = None,
        hostname: Annotated[
            str | None,
            Field(description="Exact hostname of the machine; resolved to system_id server-side."),
        ] = None,
        confirm: Annotated[
            bool,
            Field(description="Must be True to proceed. This operation is destructive."),
        ] = False,
    ) -> StatusOperation:
        system_id = await resolve_system_id(client, system_id, hostname)
        _validate_ids(system_id, block_device_id=block_device_id)
        if confirm is not True:
            raise ValueError(
                "unmount_block_device can break in-use mounts; verify the "
                "target is correct and pass confirm=True. "
                f"Affected: system_id={system_id}, hostname={hostname}, block_device_id={block_device_id}"
            )
        await client.post(unmount_block_device_path(system_id, block_device_id), json={})
        return {
            "status": "ok",
            "system_id": system_id,
            "resource_id": block_device_id,
            "operation": "unmount",
        }
