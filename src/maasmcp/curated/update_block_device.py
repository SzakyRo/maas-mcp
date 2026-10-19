"""update_block_device: PUT /nodes/{system_id}/blockdevices/{id}/."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.storage import StatusOperation
from maasmcp.curated._storage_paths import _validate_ids, block_device_path
from maasmcp.maas.client import MaasClient


class UpdateBlockDeviceTool:
    name = "update_block_device"
    description = (
        "Update a block device's metadata (name, model, serial, id_path) and — "
        "on Ready machines — size (logical volumes only), block_size, or uuid. "
        "Use this to rename a disk, correct its reported identifiers after "
        "discovery, or resize a logical volume; call list_block_devices or get "
        "the machine to obtain the id. "
        "Returns {'status': 'ok', 'system_id', 'resource_id', 'operation': 'update'}. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        block_device_id: Annotated[
            int, Field(description="MAAS id of the block device to update.")
        ],
        *,
        system_id: Annotated[
            str | None,
            Field(
                description="MAAS system_id of the machine. "
                "Provide this or hostname, exactly one."
            ),
        ] = None,
        name: Annotated[
            str | None, Field(description="New human-readable name for the device.")
        ] = None,
        model: Annotated[str | None, Field(description="Disk model string.")] = None,
        serial: Annotated[str | None, Field(description="Disk serial number string.")] = None,
        id_path: Annotated[str | None, Field(description="udev id_path for the disk.")] = None,
        size: Annotated[
            str | None,
            Field(
                description="New size in bytes (or with one unit suffix, e.g. '100G'). "
                "Only allowed for logical volumes."
            ),
        ] = None,
        block_size: Annotated[
            str | None, Field(description="New block size for the device (physical devices only).")
        ] = None,
        uuid: Annotated[str | None, Field(description="New uuid for the device.")] = None,
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
        _validate_ids(system_id, block_device_id=block_device_id)
        if confirm is not True:
            raise ValueError(
                "update_block_device mutates MAAS state; pass confirm=True to proceed. "
                f"Affected: system_id={system_id}, hostname={hostname}, block_device_id={block_device_id}"
            )
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if model is not None:
            body["model"] = model
        if serial is not None:
            body["serial"] = serial
        if id_path is not None:
            body["id_path"] = id_path
        if size is not None:
            body["size"] = size
        if block_size is not None:
            body["block_size"] = block_size
        if uuid is not None:
            body["uuid"] = uuid
        await client.put(block_device_path(system_id, block_device_id), json=body)
        return {
            "status": "ok",
            "system_id": system_id,
            "resource_id": block_device_id,
            "operation": "update",
        }
