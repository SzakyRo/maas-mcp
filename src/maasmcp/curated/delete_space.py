"""delete_space: DELETE /spaces/{id}/."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import _validate_id, space_path
from maasmcp.maas.client import MaasClient


class DeleteSpaceTool:
    name = "delete_space"
    description = (
        "Delete a space from MAAS. "
        "Use this only after removing all subnets and VLANs assigned to the space "
        "(see update_subnet, update_vlan, list_spaces, and get_space). "
        "Returns nothing on success. "
        "DESTRUCTIVE (cluster-wide) — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        space_id: Annotated[int, Field(description="MAAS id of the space to delete.")],
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> None:
        _validate_id(space_id=space_id)
        if confirm is not True:
            raise ValueError(
                "delete_space is destructive; pass confirm=True to proceed. "
                f"Affected: space_id={space_id}"
            )
        await client.delete(space_path(space_id))
