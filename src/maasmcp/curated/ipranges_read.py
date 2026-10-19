"""ipranges_read: GET /ipranges/ (raw read of the collection)."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.maas.client import MaasClient


class IprangesReadTool:
    name = "ipranges_read"
    description = (
        "Read IP ranges in MAAS via the collection endpoint. "
        "Use this when you need the raw MAAS response; for browsing IP ranges, "
        "the curated list_ip_ranges is preferred. "
        "Returns a list of IP range dicts (or the raw collection). "
        "Read-only; no confirmation needed."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        paginate: Annotated[
            bool,
            Field(
                description="Set to True to auto-paginate through limit/offset up to max_paginated_items. "
                "False (default) returns a single MAAS page."
            ),
        ] = False,
    ) -> list[dict[str, Any]] | dict[str, Any] | None:
        path = "/api/2.0/ipranges/"
        # Strip the internal ``paginate`` flag before sending — MAAS
        # would treat it as a query param and 302-redirect us.
        params: dict[str, Any] = {}
        return await client.paginated_get(path, params=params, paginate=paginate)  # type: ignore[no-any-return]
