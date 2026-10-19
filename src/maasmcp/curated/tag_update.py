"""tag_update: PUT /api/2.0/tags/{name}/."""

from __future__ import annotations

from typing import Annotated, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._schemas.access import Tag
from maasmcp.curated._storage_paths import quote_segment
from maasmcp.maas.client import MaasClient


class TagUpdateTool:
    name = "tag_update"
    description = (
        "Update a tag's comment or definition in MAAS (PUT /tags/{name}/), or "
        "rename it via new_name. Renaming or changing the definition re-triggers "
        "MAAS's tag-to-node mapping rebuild. "
        "Returns the updated tag object. "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        name: Annotated[str, Field(description="Name of the tag to update.")],
        new_name: Annotated[
            str | None,
            Field(
                description="Rename the tag to this name. Because the name is used in URLs, "
                "it should be short."
            ),
        ] = None,
        comment: Annotated[
            str | None,
            Field(
                description="A description of what the the tag will be used for in natural language."
            ),
        ] = None,
        definition: Annotated[
            str | None,
            Field(
                description="An XPATH query that is evaluated against the hardware_details stored for all nodes (i.e. the output of ``lshw -xml``)."
            ),
        ] = None,
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> Tag | None:
        if confirm is not True:
            raise ValueError(
                "tag_update is destructive; pass confirm=True to proceed. "
                f"Affected: name={name}, new_name={new_name!r}, comment={comment!r}, "
                f"definition={definition!r}"
            )
        body = {
            k: v
            for k, v in {"name": new_name, "comment": comment, "definition": definition}.items()
            if v is not None
        }
        return cast(
            Tag | None,
            await client.put(f"/api/2.0/tags/{quote_segment(name)}/", json=body),
        )
