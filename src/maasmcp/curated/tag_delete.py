"""tag_delete: DELETE /api/2.0/tags/{name}/."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._storage_paths import quote_segment
from maasmcp.maas.client import MaasClient


class TagDeleteTool:
    name = "tag_delete"
    description = (
        "Delete a tag in MAAS. "
        "Use this for direct MAAS API access when no curated verb exists. "
        "Returns nothing on success. "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        name: Annotated[str, Field(description="Name of the tag to delete.")],
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> None:
        if confirm is not True:
            raise ValueError(
                f"tag_delete is destructive; pass confirm=True to proceed. Affected: name={name}"
            )
        await client.delete(f"/api/2.0/tags/{quote_segment(name)}/")
