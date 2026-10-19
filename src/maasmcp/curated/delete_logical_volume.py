"""delete_logical_volume: POST /nodes/{system_id}/volume-group/{vg_id}/op-delete_logical_volume."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._storage_paths import _validate_ids, lv_delete_path
from maasmcp.maas.client import MaasClient


class DeleteLogicalVolumeTool:
    name = "delete_logical_volume"
    description = (
        "Delete a logical volume from a MAAS volume group. "
        "Use this to remove an LV after unmounting it and stopping any services "
        "that depend on it (see list_volume_groups and get_volume_group). "
        "Returns nothing on success (MAAS returns 204, even if the LV id does not "
        "exist). "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        vg_id: Annotated[int, Field(description="MAAS id of the volume group that owns the LV.")],
        lv_id: Annotated[int, Field(description="MAAS id of the logical volume to delete.")],
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
    ) -> None:
        system_id = await resolve_system_id(client, system_id, hostname)
        _validate_ids(system_id, vg_id=vg_id)
        if lv_id <= 0:
            raise ValueError(f"lv_id must be > 0, got {lv_id}")
        if confirm is not True:
            raise ValueError(
                "delete_logical_volume is destructive; pass confirm=True to proceed. "
                f"Affected: system_id={system_id}, hostname={hostname}, vg_id={vg_id}, lv_id={lv_id}"
            )
        await client.post(lv_delete_path(system_id, vg_id), json={"id": lv_id})
