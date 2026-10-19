"""tags_create: POST /api/2.0/tags/."""

from __future__ import annotations

from typing import Annotated, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._schemas.access import Tag
from maasmcp.maas.client import MaasClient


class TagsCreateTool:
    name = "tags_create"
    description = (
        "Create a tag in MAAS. "
        "Use this for direct MAAS API access when no curated verb exists; "
        "see tag_machine and untag_machine to apply tags to machines. "
        "Returns the MAAS response. "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        name: Annotated[
            str,
            Field(
                description="The new tag name. Because the name will be used in urls, it should be short."
            ),
        ],
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
        kernel_opts: Annotated[
            str | None,
            Field(
                description="Nodes associated with this tag will add this string to their kernel options when booting. The value overrides the global ``kernel_opts`` setting. If more than one tag is associated with a node, command line will be concatenated from all associated tags, in alphabetic tag name order."
            ),
        ] = None,
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> Tag | None:
        if confirm is not True:
            raise ValueError(
                f"tags_create is destructive; pass confirm=True to proceed. Affected: name={name}"
            )
        body = {
            k: v
            for k, v in {
                "name": name,
                "comment": comment,
                "definition": definition,
                "kernel_opts": kernel_opts,
            }.items()
            if v is not None
        }
        return cast(Tag | None, await client.post("/api/2.0/tags/", json=body))
