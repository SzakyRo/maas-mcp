"""delete_volume_group: DELETE /nodes/{system_id}/volume-group/{id}/."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._storage_paths import _validate_ids, volume_group_path
from maasmcp.maas.client import MaasClient


class DeleteVolumeGroupTool:
    name = "delete_volume_group"
    description = (
        "Delete a volume group on a machine. "
        "Use this to tear down a VG after its logical volumes have been deleted "
        "(see delete_logical_volume and list_volume_groups). "
        "Returns nothing on success. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        vg_id: Annotated[int, Field(description="MAAS id of the volume group to delete.")],
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
        if confirm is not True:
            raise ValueError(
                "delete_volume_group is destructive; pass confirm=True to proceed. "
                f"Affected: system_id={system_id}, hostname={hostname}, vg_id={vg_id}"
            )
        await client.delete(volume_group_path(system_id, vg_id))
