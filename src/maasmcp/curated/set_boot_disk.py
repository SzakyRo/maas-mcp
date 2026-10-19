"""set_boot_disk: POST /nodes/{system_id}/blockdevices/{id}/op-set_boot_disk."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.storage import StatusOperation
from maasmcp.curated._storage_paths import _validate_ids, set_boot_disk_path
from maasmcp.maas.client import MaasClient


class SetBootDiskTool:
    name = "set_boot_disk"
    description = (
        "Designate a block device as the boot disk for a MAAS machine. "
        "Use after listing block devices with list_block_devices or storage_summary; "
        "an incorrect choice can prevent the machine from booting. "
        "Returns {'status': 'ok', 'system_id': ..., 'resource_id': block_device_id, "
        "'operation': 'set_boot_disk'}. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        block_device_id: Annotated[
            int,
            Field(description="ID of the block device to set as the boot disk."),
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
            bool,
            Field(description="Must be True to proceed. This operation is destructive."),
        ] = False,
    ) -> StatusOperation:
        system_id = await resolve_system_id(client, system_id, hostname)
        _validate_ids(system_id, block_device_id=block_device_id)
        if confirm is not True:
            raise ValueError(
                "set_boot_disk changes which disk the machine boots from; "
                "wrong choice can brick it. Pass confirm=True. "
                f"Affected: system_id={system_id}, hostname={hostname}, block_device_id={block_device_id}"
            )
        # MAAS returns literal "OK" text on success, not JSON. Callers may
        # pass an empty dict too — MaasClient normalizes empty bodies to no
        # body (MAAS rejects empty multipart with 400); the response parser
        # tolerates the text response either way.
        await client.post(set_boot_disk_path(system_id, block_device_id))
        return {
            "status": "ok",
            "system_id": system_id,
            "resource_id": block_device_id,
            "operation": "set_boot_disk",
        }
