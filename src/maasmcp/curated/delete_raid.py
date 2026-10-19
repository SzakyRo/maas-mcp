"""delete_raid: DELETE /nodes/{system_id}/raid/{id}/."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._storage_paths import _validate_ids, raid_path
from maasmcp.maas.client import MaasClient


class DeleteRaidTool:
    name = "delete_raid"
    description = (
        "Delete a RAID array from a MAAS machine. "
        "Use this to tear down a RAID array after stopping any volume groups or "
        "filesystems that depend on it (see list_raids and get_raid). "
        "Returns nothing on success (MAAS 204). "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        raid_id: Annotated[int, Field(description="MAAS id of the RAID array to delete.")],
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
        _validate_ids(system_id, raid_id=raid_id)
        if confirm is not True:
            raise ValueError(
                "delete_raid is destructive; pass confirm=True to proceed. "
                f"Affected: system_id={system_id}, hostname={hostname}, raid_id={raid_id}"
            )
        await client.delete(raid_path(system_id, raid_id))
