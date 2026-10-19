"""list_block_devices: GET /nodes/{system_id}/blockdevices/."""

from __future__ import annotations

from typing import Annotated, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.storage import BlockDevice
from maasmcp.curated._storage_paths import _validate_ids, block_devices_path
from maasmcp.maas.client import MaasClient


class ListBlockDevicesTool:
    name = "list_block_devices"
    description = (
        "List all block devices on a MAAS machine. "
        "Use this before get_block_device, create_partition, create_raid, or "
        "set_boot_disk to discover device ids. "
        "Returns a list of MAAS block-device dicts (id, name, size, type, "
        "partitions, etc.). "
        "Accepts system_id or hostname (provide exactly one). "
        "Read-only; no confirmation needed."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        system_id: Annotated[
            str | None,
            Field(
                description="MAAS system_id of the machine. "
                "Provide this or hostname, exactly one."
            ),
        ] = None,
        *,
        hostname: Annotated[
            str | None,
            Field(description="Exact hostname of the machine; resolved to system_id server-side."),
        ] = None,
    ) -> list[BlockDevice]:
        system_id = await resolve_system_id(client, system_id, hostname)
        _validate_ids(system_id)
        resp = await client.get(block_devices_path(system_id))
        if isinstance(resp, dict) and "blockdevices" in resp:
            return cast(list[BlockDevice], list(resp["blockdevices"]))
        if isinstance(resp, list):
            return cast(list[BlockDevice], resp)
        return []
