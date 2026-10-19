"""get_partition: GET /nodes/{system_id}/blockdevices/{device_id}/partitions/{id}."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.storage import Partition
from maasmcp.curated._storage_paths import _validate_ids, partition_path
from maasmcp.maas.client import MaasClient


class GetPartitionTool:
    name = "get_partition"
    description = (
        "Fetch one partition on a machine's block device. "
        "Use this after list_block_devices and list_partitions to discover "
        "system_id, block_device_id, and partition_id. "
        "Returns the MAAS partition dict (id, uuid, path, size, filesystem, etc.). "
        "Accepts system_id or hostname (provide exactly one). "
        "Read-only; no confirmation needed."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        block_device_id: Annotated[int, Field(description="MAAS id of the block device.")],
        partition_id: Annotated[int, Field(description="MAAS id of the partition.")],
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
    ) -> Partition:
        system_id = await resolve_system_id(client, system_id, hostname)
        _validate_ids(system_id, block_device_id=block_device_id, partition_id=partition_id)
        resp: Partition = await client.get(partition_path(system_id, block_device_id, partition_id))
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for partition {partition_id} "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return resp
