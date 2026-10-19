"""delete_partition: DELETE /nodes/{system_id}/blockdevices/{device_id}/partitions/{id}."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.storage import StatusOperation
from maasmcp.curated._storage_paths import _validate_ids, partition_path
from maasmcp.maas.client import MaasClient


class DeletePartitionTool:
    name = "delete_partition"
    description = (
        "Delete a partition from a block device. "
        "Use this to remove a partition after unmounting it and deleting any "
        "filesystem, RAID, or volume group references (see list_partitions and "
        "delete_volume_group). "
        "Returns {'status': 'ok', 'system_id': ..., 'resource_id': ..., "
        "'operation': 'delete'}. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — wipes the filesystem and data; must pass confirm=True; "
        "rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        block_device_id: Annotated[
            int, Field(description="MAAS id of the block device that owns the partition.")
        ],
        partition_id: Annotated[int, Field(description="MAAS id of the partition to delete.")],
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
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> StatusOperation:
        system_id = await resolve_system_id(client, system_id, hostname)
        _validate_ids(system_id, block_device_id=block_device_id, partition_id=partition_id)
        if confirm is not True:
            raise ValueError(
                "delete_partition wipes the filesystem and data; pass confirm=True. "
                f"Affected: system_id={system_id}, hostname={hostname}, block_device_id={block_device_id}, "
                f"partition_id={partition_id}"
            )
        await client.delete(partition_path(system_id, block_device_id, partition_id))
        return {
            "status": "ok",
            "system_id": system_id,
            "resource_id": partition_id,
            "operation": "delete",
        }
