"""subnets_read: GET /subnets/ (raw read of the collection)."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.maas.client import MaasClient


class SubnetsReadTool:
    name = "subnets_read"
    description = (
        "Read subnets in MAAS via the collection endpoint. "
        "Use this when you need the raw MAAS response; for browsing subnets, "
        "the curated list_subnets is preferred. "
        "Returns a list of subnet dicts (or the raw collection). "
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
        path = "/api/2.0/subnets/"
        # Strip the internal ``paginate`` flag before sending — MAAS
        # would treat it as a query param and 302-redirect us.
        params: dict[str, Any] = {}
        return await client.paginated_get(path, params=params, paginate=paginate)  # type: ignore[no-any-return]
