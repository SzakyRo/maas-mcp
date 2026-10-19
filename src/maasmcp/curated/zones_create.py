"""zones_create: POST /api/2.0/zones/."""

from __future__ import annotations

from typing import Annotated, Any, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._schemas.access import Zone
from maasmcp.maas.client import MaasClient


class ZonesCreateTool:
    name = "zones_create"
    description = (
        "Create a zone in MAAS. "
        "Use this to group machines; assign machines afterwards with "
        "machines_set_zone. Fails with 400 if the zone already exists — check "
        "zones_list first. "
        "Returns the newly-created zone dict. "
        "State-mutating — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        name: Annotated[str, Field(description="The new zone's name.")],
        description: Annotated[
            str | None, Field(description="A brief description of the new zone.")
        ] = None,
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation mutates state.")
        ] = False,
    ) -> Zone:
        if not name.strip():
            raise ValueError("zones_create requires a non-empty name")
        if confirm is not True:
            raise ValueError(
                f"zones_create mutates state; pass confirm=True to proceed. Affected: name={name!r}"
            )
        body: dict[str, Any] = {"name": name}
        if description is not None:
            body["description"] = description
        resp = await client.post("/api/2.0/zones/", json=body)
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for created zone "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return cast(Zone, resp)
