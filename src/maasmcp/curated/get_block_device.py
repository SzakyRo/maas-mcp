"""get_block_device: GET /nodes/{system_id}/blockdevices/{id}/."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.storage import BlockDevice
from maasmcp.curated._storage_paths import _validate_ids, block_device_path
from maasmcp.maas.client import MaasClient


class GetBlockDeviceTool:
    name = "get_block_device"
    description = (
        "Fetch one block device. "
        "Use this after list_block_devices to inspect a specific disk. "
        "Returns the full MAAS block device dict. "
        "Accepts system_id or hostname (provide exactly one). "
        "Read-only; no confirmation needed."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        block_device_id: Annotated[int, Field(description="MAAS id of the block device to fetch.")],
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
    ) -> BlockDevice:
        system_id = await resolve_system_id(client, system_id, hostname)
        _validate_ids(system_id, block_device_id=block_device_id)
        resp: BlockDevice = await client.get(block_device_path(system_id, block_device_id))
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for block device {block_device_id} "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return resp
