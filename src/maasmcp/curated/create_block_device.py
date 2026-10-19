"""create_block_device: POST /nodes/{system_id}/blockdevices/."""

from __future__ import annotations

from typing import Annotated, Any, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.storage import BlockDevice
from maasmcp.curated._storage_paths import _validate_ids, block_devices_path
from maasmcp.maas.client import MaasClient


class CreateBlockDeviceTool:
    name = "create_block_device"
    description = (
        "Create a physical block device on a MAAS machine. "
        "Use this to add a disk to an existing machine before partitioning, "
        "formatting, or building RAID. "
        "Returns the newly-created block device dict. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        name: Annotated[str, Field(description="Human-readable name for the new block device.")],
        size: Annotated[str, Field(description="Size of the block device (e.g. '500G', '1T').")],
        block_size: Annotated[str, Field(description="Block size for the device (e.g. '4096').")],
        *,
        system_id: Annotated[
            str | None,
            Field(
                description="MAAS system_id of the machine. "
                "Provide this or hostname, exactly one."
            ),
        ] = None,
        model: Annotated[str | None, Field(description="Disk model string.")] = None,
        serial: Annotated[str | None, Field(description="Disk serial string.")] = None,
        id_path: Annotated[str | None, Field(description="udev id_path for the disk.")] = None,
        hostname: Annotated[
            str | None,
            Field(description="Exact hostname of the machine; resolved to system_id server-side."),
        ] = None,
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> BlockDevice:
        system_id = await resolve_system_id(client, system_id, hostname)
        _validate_ids(system_id)
        if not name:
            raise ValueError("name must be a non-empty string")
        if confirm is not True:
            raise ValueError(
                "create_block_device is destructive; pass confirm=True to proceed. "
                f"Affected: system_id={system_id}, hostname={hostname}, name={name}"
            )
        body: dict[str, Any] = {
            "name": name,
            "size": size,
            "block_size": block_size,
        }
        if model is not None:
            body["model"] = model
        if serial is not None:
            body["serial"] = serial
        if id_path is not None:
            body["id_path"] = id_path
        resp = await client.post(block_devices_path(system_id), json=body)
        if isinstance(resp, dict):
            return cast(BlockDevice, resp)
        return cast(BlockDevice, {})
