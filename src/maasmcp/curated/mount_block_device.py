"""mount_block_device: POST /nodes/{system_id}/blockdevices/{id}/op-mount.

Mirror of :class:`MountPartitionTool` for whole block devices (RAIDs, VGs).
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.storage import StatusOperation
from maasmcp.curated._storage_paths import _validate_ids, mount_block_device_path
from maasmcp.maas.client import MaasClient


class MountBlockDeviceTool:
    name = "mount_block_device"
    description = (
        "Mount a filesystem on a whole block device (RAID, volume group, or raw "
        "disk) at a given mount point. "
        "Use after identifying the target with list_block_devices or storage_summary; "
        "for partitions, use mount_partition instead. "
        "Returns {'status': 'ok', 'system_id': ..., 'resource_id': block_device_id, "
        "'operation': 'mount'}. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        block_device_id: Annotated[int, Field(description="ID of the block device to mount.")],
        mount_point: Annotated[
            str,
            Field(description="Absolute path where the filesystem should be mounted (e.g. /data)."),
        ],
        *,
        system_id: Annotated[
            str | None,
            Field(
                description="MAAS system_id of the machine. "
                "Provide this or hostname, exactly one."
            ),
        ] = None,
        mount_options: Annotated[
            str | None,
            Field(description="Optional mount options string passed to the filesystem mount."),
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
        if not mount_point or not mount_point.startswith("/"):
            raise ValueError(f"mount_point must start with '/', got {mount_point!r}")
        if confirm is not True:
            raise ValueError(
                "mount_block_device can shadow real filesystems; verify the "
                "target is correct and pass confirm=True. "
                f"Affected: system_id={system_id}, hostname={hostname}, block_device_id={block_device_id}, "
                f"mount_point={mount_point}"
            )
        body: dict[str, Any] = {"mount_point": mount_point}
        if mount_options is not None:
            body["mount_options"] = mount_options
        await client.post(mount_block_device_path(system_id, block_device_id), json=body)
        return {
            "status": "ok",
            "system_id": system_id,
            "resource_id": block_device_id,
            "operation": "mount",
        }
