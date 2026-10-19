"""zone_delete: DELETE /api/2.0/zones/{name}/."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._storage_paths import quote_segment
from maasmcp.maas.client import MaasClient


class ZoneDeleteTool:
    name = "zone_delete"
    description = (
        "Delete a zone in MAAS (zones are name-addressed). The built-in 'default' "
        "zone always exists and cannot be removed; empty the zone first via "
        "machines_set_zone on its members if MAAS refuses. "
        "Returns nothing on success (HTTP 204). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        name: Annotated[str, Field(description="Name of the zone to delete.")],
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> None:
        if confirm is not True:
            raise ValueError(
                f"zone_delete is destructive; pass confirm=True to proceed. Affected: name={name!r}"
            )
        await client.delete(f"/api/2.0/zones/{quote_segment(name)}/")
