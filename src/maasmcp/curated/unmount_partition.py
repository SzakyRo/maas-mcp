"""unmount_partition: POST /nodes/{system_id}/blockdevices/{device_id}/partitions/{id}?op=unmount."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.storage import StatusOperation
from maasmcp.curated._storage_paths import _validate_ids, unmount_partition_path
from maasmcp.maas.client import MaasClient


class UnmountPartitionTool:
    name = "unmount_partition"
    description = (
        "Unmount a mounted filesystem on a partition. "
        "Use this before reformatting or reconfiguring storage that is currently "
        "mounted; verify the target is correct before confirming. "
        "Returns {'status': 'ok', 'system_id', 'resource_id', 'operation': 'unmount'}. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        block_device_id: Annotated[
            int, Field(description="MAAS id of the block device containing the partition.")
        ],
        partition_id: Annotated[int, Field(description="MAAS id of the partition to unmount.")],
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
        _validate_ids(system_id, block_device_id=block_device_id, partition_id=partition_id)
        if confirm is not True:
            raise ValueError(
                "unmount_partition can disrupt running services; verify "
                "the target is correct and pass confirm=True. "
                f"Affected: system_id={system_id}, hostname={hostname}, block_device_id={block_device_id}, "
                f"partition_id={partition_id}"
            )
        await client.post(
            unmount_partition_path(system_id, block_device_id, partition_id),
            json={},
            params={"op": "unmount"},
        )
        return {
            "status": "ok",
            "system_id": system_id,
            "resource_id": partition_id,
            "operation": "unmount",
        }
