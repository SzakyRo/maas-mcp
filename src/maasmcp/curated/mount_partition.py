"""mount_partition: POST /nodes/{system_id}/blockdevices/{device_id}/partitions/{id}?op=mount."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.storage import StatusOperation
from maasmcp.curated._storage_paths import _validate_ids, mount_partition_path
from maasmcp.maas.client import MaasClient


class MountPartitionTool:
    name = "mount_partition"
    description = (
        "Mount a filesystem on an existing partition at a given mount point. "
        "Use after identifying the target partition with list_partitions or "
        "storage_summary; for whole block devices, use mount_block_device instead. "
        "Returns {'status': 'ok', 'system_id': ..., 'resource_id': partition_id, "
        "'operation': 'mount'}. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        block_device_id: Annotated[
            int,
            Field(description="ID of the block device that owns the partition."),
        ],
        partition_id: Annotated[int, Field(description="ID of the partition to mount.")],
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
        _validate_ids(system_id, block_device_id=block_device_id, partition_id=partition_id)
        if not mount_point or not mount_point.startswith("/"):
            raise ValueError(f"mount_point must start with '/', got {mount_point!r}")
        if confirm is not True:
            raise ValueError(
                "mount_partition can shadow real filesystems; verify the "
                "target is correct and pass confirm=True. "
                f"Affected: system_id={system_id}, hostname={hostname}, block_device_id={block_device_id}, "
                f"partition_id={partition_id}, mount_point={mount_point}"
            )
        body: dict[str, Any] = {"mount_point": mount_point}
        if mount_options is not None:
            body["mount_options"] = mount_options
        await client.post(
            mount_partition_path(system_id, block_device_id, partition_id),
            json=body,
            params={"op": "mount"},
        )
        return {
            "status": "ok",
            "system_id": system_id,
            "resource_id": partition_id,
            "operation": "mount",
        }
