"""tags_read: GET /api/2.0/tags/."""

from __future__ import annotations

from typing import Annotated, Any, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._schemas.access import Tag
from maasmcp.maas.client import MaasClient


class TagsReadTool:
    name = "tags_read"
    description = (
        "Read tags in MAAS. "
        "Alias of tags_list (identical GET /tags/ collection read, kept for "
        "client compatibility) — prefer tags_list. "
        "Returns a list of tag objects or the raw collection. "
        "Read-only; no confirmation needed."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        paginate: Annotated[
            bool,
            Field(
                description="Set to True to auto-paginate through limit/offset up to max_paginated_items. False (default) returns a single MAAS page."
            ),
        ] = False,
    ) -> list[Tag] | dict[str, Any] | None:
        # ``paginate`` is local-only — sending it as a query param would
        # trigger a MAAS 302 redirect.
        params: dict[str, Any] = {}
        return cast(
            list[Tag] | dict[str, Any] | None,
            await client.paginated_get("/api/2.0/tags/", params=params, paginate=paginate),
        )
