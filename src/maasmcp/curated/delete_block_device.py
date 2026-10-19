"""delete_block_device: DELETE /nodes/{system_id}/blockdevices/{id}/."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._storage_paths import _validate_ids, block_device_path
from maasmcp.maas.client import MaasClient


class DeleteBlockDeviceTool:
    name = "delete_block_device"
    description = (
        "Delete a block device from a MAAS machine. "
        "Use this to remove a disk after any partitions, RAID arrays, and volume "
        "groups that reference it have been deleted (see delete_partition, "
        "delete_raid, delete_volume_group, and list_block_devices). "
        "Returns {'status': 'ok', 'system_id': ..., 'resource_id': ..., "
        "'operation': 'delete'}. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE and irreversible — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        block_device_id: Annotated[
            int, Field(description="MAAS id of the block device to delete.")
        ],
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
    ) -> dict[str, Any]:
        system_id = await resolve_system_id(client, system_id, hostname)
        _validate_ids(system_id, block_device_id=block_device_id)
        if confirm is not True:
            raise ValueError(
                "delete_block_device is destructive and irreversible; "
                f"pass confirm=True to proceed. Affected: system_id={system_id}, "
                f"hostname={hostname}, block_device_id={block_device_id}"
            )
        await client.delete(block_device_path(system_id, block_device_id))
        return {
            "status": "ok",
            "system_id": system_id,
            "resource_id": block_device_id,
            "operation": "delete",
        }
