"""list_partitions: GET /nodes/{system_id}/blockdevices/{device_id}/partitions/."""

from __future__ import annotations

from typing import Annotated, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.storage import Partition
from maasmcp.curated._storage_paths import _validate_ids, block_device_path, partitions_path
from maasmcp.maas.client import MaasClient
from maasmcp.maas.errors import MCPUpstreamError

# MAAS 500s with this exact body when the block device has no PartitionTable
# row at all (fresh unused disks, raw whole-disk RAID members). Undocumented
# upstream defect — docs/reference/maasapi.md lists only 200/404 for this endpoint — so we
# match the verbatim phrase rather than the status code alone.
_NO_PARTITION_TABLE_PHRASE = "PartitionTable matching query does not exist"


def _is_missing_partition_table(exc: MCPUpstreamError) -> bool:
    return exc.status_code == 500 and _NO_PARTITION_TABLE_PHRASE in (exc.detail or "")


class ListPartitionsTool:
    name = "list_partitions"
    description = (
        "List all partitions on a block device. Use this before "
        "format_partition, mount_partition, or delete_partition. Returns a "
        "list of partition dicts; a device with no partition table yields "
        "an empty list (MAAS 500s on that case upstream — we fall back to "
        "the block device's inline partition listing). "
        "Accepts system_id or hostname (provide exactly one). "
        "Read-only; no confirmation needed."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        block_device_id: Annotated[
            int, Field(description="ID of the block device whose partitions to list.")
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
    ) -> list[Partition]:
        system_id = await resolve_system_id(client, system_id, hostname)
        _validate_ids(system_id, block_device_id=block_device_id)
        try:
            resp = await client.get(partitions_path(system_id, block_device_id))
        except MCPUpstreamError as exc:
            if not _is_missing_partition_table(exc):
                raise
            # Table-less disk: the /partitions/ sub-endpoint 500s, but the
            # block device record serves inline partitions reliably (and an
            # empty list there is the semantically correct answer anyway).
            device = await client.get(block_device_path(system_id, block_device_id))
            if isinstance(device, dict):
                return cast(list[Partition], list(device.get("partitions") or []))
            return []
        if isinstance(resp, dict) and "partitions" in resp:
            return cast(list[Partition], list(resp["partitions"]))
        if isinstance(resp, list):
            return cast(list[Partition], resp)
        return []
