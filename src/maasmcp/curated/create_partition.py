"""create_partition: POST /nodes/{system_id}/blockdevices/{device_id}/partitions/."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.storage import Partition
from maasmcp.curated._storage_paths import _validate_ids, partitions_path
from maasmcp.maas.client import MaasClient


class CreatePartitionTool:
    name = "create_partition"
    description = (
        "Create a partition on a block device. "
        "MAAS only accepts size, uuid (GPT partition tables), and bootable here — "
        "the filesystem is set afterwards with format_partition, and the partition "
        "table type is derived from the disk. "
        "Use after acquiring or inspecting a machine's disks; for logical volumes "
        "use create_logical_volume instead. "
        "Returns the newly-created partition dict. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        block_device_id: Annotated[
            int, Field(description="MAAS id of the block device to partition.")
        ],
        *,
        system_id: Annotated[
            str | None,
            Field(
                description="MAAS system_id of the machine. "
                "Provide this or hostname, exactly one."
            ),
        ] = None,
        size: Annotated[
            str | None,
            Field(
                description="Size of the partition in bytes, or a number with one unit "
                "suffix such as '100G' or '500M' (no %, no 'remaining'). "
                "Omit to use all available space."
            ),
        ] = None,
        uuid: Annotated[
            str | None,
            Field(
                description="UUID for the partition. Only used if the partition table "
                "type for the block device is GPT."
            ),
        ] = None,
        bootable: Annotated[
            bool | None, Field(description="Mark the partition as bootable.")
        ] = None,
        hostname: Annotated[
            str | None,
            Field(description="Exact hostname of the machine; resolved to system_id server-side."),
        ] = None,
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> Partition:
        system_id = await resolve_system_id(client, system_id, hostname)
        _validate_ids(system_id, block_device_id=block_device_id)
        if size is not None and not str(size).strip():
            raise ValueError("size must be a non-empty string or omitted (all available space)")
        if confirm is not True:
            raise ValueError(
                "create_partition alters the partition table; pass confirm=True. "
                f"Affected: system_id={system_id}, hostname={hostname}, block_device_id={block_device_id}, "
                f"size={size}"
            )
        body: dict[str, Any] = {}
        if size is not None:
            body["size"] = size
        if uuid is not None:
            body["uuid"] = uuid
        if bootable is not None:
            body["bootable"] = bootable
        resp: Partition = await client.post(partitions_path(system_id, block_device_id), json=body)
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for created partition "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return resp
