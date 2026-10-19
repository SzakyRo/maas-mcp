"""update_space: PUT /spaces/{id}/."""

from __future__ import annotations

from typing import Annotated, Any, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import _validate_id, space_path
from maasmcp.curated._schemas.network import Space
from maasmcp.maas.client import MaasClient


class UpdateSpaceTool:
    name = "update_space"
    description = (
        "Update a space's name or description. "
        "Use this to rename or document an existing space; create a new space "
        "with create_space. MAAS treats name as required for this op, so when you "
        "only want to change the description, pass the current name along. "
        "Returns the updated space dict. "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        space_id: Annotated[
            int,
            Field(
                description="MAAS id of the space to update (0 is the built-in 'undefined' space)."
            ),
        ],
        name: Annotated[
            str,
            Field(description="The space's name. Required by MAAS even when unchanged."),
        ],
        description: Annotated[str | None, Field(description="New space description.")] = None,
        confirm: Annotated[
            bool,
            Field(description="Must be True to proceed. This operation is destructive."),
        ] = False,
    ) -> Space:
        _validate_id(space_id=space_id, _allow_zero=True)
        if not name.strip():
            raise ValueError("update_space requires a non-empty name (MAAS marks it required).")
        if confirm is not True:
            raise ValueError(
                "update_space is destructive; pass confirm=True to proceed. "
                f"Affected: space_id={space_id}"
            )
        body: dict[str, Any] = {"name": name}
        if description is not None:
            body["description"] = description
        resp = await client.put(space_path(space_id), json=body)
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for updated space "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return cast(Space, resp)
