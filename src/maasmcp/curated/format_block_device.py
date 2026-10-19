"""format_block_device: POST /nodes/{system_id}/blockdevices/{id}/op-format."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.storage import StatusOperation
from maasmcp.curated._storage_paths import _validate_ids, format_block_device_path
from maasmcp.maas.client import MaasClient


class FormatBlockDeviceTool:
    name = "format_block_device"
    description = (
        "Format a block device with a filesystem. "
        "Use this before mounting or deploying a machine that uses a raw disk. "
        "Returns a status dict with status='ok', system_id, resource_id, and "
        "operation='format'. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — wipes existing data on the device; must pass confirm=True; "
        "rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        block_device_id: Annotated[
            int, Field(description="MAAS id of the block device to format.")
        ],
        fstype: Annotated[
            str,
            Field(
                description="Filesystem type to create (e.g. 'ext4', 'xfs'). "
                "Note: 'raid' is not formattable — MAAS marks RAID members "
                "automatically when they join an array via create_raid."
            ),
        ],
        *,
        system_id: Annotated[
            str | None,
            Field(
                description="MAAS system_id of the machine. "
                "Provide this or hostname, exactly one."
            ),
        ] = None,
        uuid: Annotated[
            str | None, Field(description="Optional filesystem UUID to assign.")
        ] = None,
        label: Annotated[
            str | None, Field(description="Optional filesystem label to assign.")
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
        _validate_ids(system_id, block_device_id=block_device_id)
        if not fstype:
            raise ValueError("fstype must be a non-empty string")
        if fstype == "raid":
            # Verified against live MAAS (0.8.1 era): op=format with
            # fstype=raid 400s — 'raid' is not in MAAS's formattable fstype
            # set. Membership is established by create_raid (which attaches
            # raw block devices and marks them), so fail fast with the
            # actionable route instead of an opaque upstream 400.
            raise ValueError(
                "'raid' is not a formattable filesystem type: MAAS marks RAID "
                "members automatically when they are joined with create_raid "
                "(pass block_devices or partitions). Do not format members by hand."
            )
        if confirm is not True:
            raise ValueError(
                "format_block_device wipes existing data; pass confirm=True to proceed. "
                f"Affected: system_id={system_id}, hostname={hostname}, block_device_id={block_device_id}, "
                f"fstype={fstype}"
            )
        body: dict[str, Any] = {"fstype": fstype}
        if uuid is not None:
            body["uuid"] = uuid
        if label is not None:
            body["label"] = label
        await client.post(format_block_device_path(system_id, block_device_id), json=body)
        return {
            "status": "ok",
            "system_id": system_id,
            "resource_id": block_device_id,
            "operation": "format",
        }
