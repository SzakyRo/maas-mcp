"""create_space: POST /spaces/."""

from __future__ import annotations

from typing import Annotated, Any, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import spaces_path
from maasmcp.curated._schemas.network import Space
from maasmcp.maas.client import MaasClient


class CreateSpaceTool:
    name = "create_space"
    description = (
        "Create a space in MAAS. "
        "Use this to group related subnets for routing/security domains before "
        "assigning subnets to the space. "
        "Returns the newly-created space dict. "
        "DESTRUCTIVE (cluster-wide) — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        name: Annotated[str, Field(description="Name for the new space.")],
        description: Annotated[
            str | None, Field(description="Optional human-readable description.")
        ] = None,
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> Space:
        if confirm is not True:
            raise ValueError(
                f"create_space is destructive; pass confirm=True to proceed. Affected: name={name}"
            )
        body: dict[str, Any] = {"name": name}
        if description is not None:
            body["description"] = description
        resp = await client.post(spaces_path(), json=body)
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for created space "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return cast(Space, resp)
