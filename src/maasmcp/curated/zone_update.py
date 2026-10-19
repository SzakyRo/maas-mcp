"""zone_update: PUT /api/2.0/zones/{name}/."""

from __future__ import annotations

from typing import Annotated, Any, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._schemas.access import Zone
from maasmcp.curated._storage_paths import quote_segment
from maasmcp.maas.client import MaasClient


class ZoneUpdateTool:
    name = "zone_update"
    description = (
        "Update a zone's name or description. Only 'name' and 'description' are "
        "honored by MAAS; other fields (id, resource-uri) are ignored. Zones are "
        "name-addressed — renaming via new_name changes the URL of subsequent "
        "zone_read/zone_update/zone_delete calls. "
        "Returns the updated zone dict. "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        name: Annotated[str, Field(description="Name of the zone to update.")],
        new_name: Annotated[
            str | None, Field(description="The zone's new name. Leave unset to keep it.")
        ] = None,
        description: Annotated[
            str | None, Field(description="A brief new description for the zone.")
        ] = None,
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> Zone:
        if new_name is None and description is None:
            raise ValueError(
                "zone_update requires new_name or description to change; both are None."
            )
        if confirm is not True:
            raise ValueError(
                f"zone_update is destructive; pass confirm=True to proceed. Affected: name={name!r}"
            )
        body: dict[str, Any] = {}
        if new_name is not None:
            body["name"] = new_name
        if description is not None:
            body["description"] = description
        resp = await client.put(f"/api/2.0/zones/{quote_segment(name)}/", json=body)
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for updated zone "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return cast(Zone, resp)
