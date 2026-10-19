"""tag_read: GET /api/2.0/tags/{name}/."""

from __future__ import annotations

from typing import Annotated, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._schemas.access import Tag
from maasmcp.curated._storage_paths import quote_segment
from maasmcp.maas.client import MaasClient


class TagReadTool:
    name = "tag_read"
    description = (
        "Read a tag in MAAS. "
        "Use this when you need the raw MAAS response or the curated verb does not exist. "
        "Returns the tag object or result. "
        "Read-only; no confirmation needed."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        name: Annotated[str, Field(description="Name of the tag to read.")],
    ) -> Tag | None:
        return cast(
            Tag | None,
            await client.get(f"/api/2.0/tags/{quote_segment(name)}/"),
        )
