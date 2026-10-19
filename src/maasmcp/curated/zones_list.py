"""zones_list: GET /api/2.0/zones/."""

from __future__ import annotations

from typing import Annotated, Any, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._schemas.access import Zone
from maasmcp.maas.client import MaasClient


class ZonesListTool:
    name = "zones_list"
    description = (
        "List all zones in MAAS (there is always at least one: 'default'). "
        "Use this to discover zone names before zone_read / zone_update / "
        "zone_delete or machines_set_zone. "
        "Returns a list of zone objects. "
        "Read-only; no confirmation needed."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        paginate: Annotated[
            bool,
            Field(
                description="Set to True to auto-paginate through limit/offset up to "
                "max_paginated_items. False (default) returns a single MAAS page."
            ),
        ] = False,
    ) -> list[Zone] | dict[str, Any] | None:
        params: dict[str, Any] = {}
        return cast(
            list[Zone] | dict[str, Any] | None,
            await client.paginated_get("/api/2.0/zones/", params=params, paginate=paginate),
        )
