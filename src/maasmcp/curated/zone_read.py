"""zone_read: GET /api/2.0/zones/{name}/."""

from __future__ import annotations

from typing import Annotated, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._schemas.access import Zone
from maasmcp.curated._storage_paths import quote_segment
from maasmcp.maas.client import MaasClient


class ZoneReadTool:
    name = "zone_read"
    description = (
        "Fetch one MAAS zone by name (zones are name-addressed, not id-addressed). "
        "Use this after zones_list to confirm a zone exists. "
        "Returns the zone dict (keys include id, name, description). "
        "Read-only; no confirmation needed."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        name: Annotated[str, Field(description="Name of the zone to fetch.")],
    ) -> Zone:
        resp = await client.get(f"/api/2.0/zones/{quote_segment(name)}/")
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for zone {name!r} "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return cast(Zone, resp)
