"""delete_fabric: DELETE /fabrics/{id}/."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import _validate_id, fabric_path
from maasmcp.maas.client import MaasClient


class DeleteFabricTool:
    name = "delete_fabric"
    description = (
        "Delete a fabric from MAAS. "
        "Use this only after deleting all VLANs and subnets within the fabric "
        "(see delete_vlan, delete_subnet, and list_fabrics). "
        "Returns nothing on success. "
        "DESTRUCTIVE (cluster-wide) — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        fabric_id: Annotated[int, Field(description="MAAS id of the fabric to delete.")],
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> None:
        _validate_id(fabric_id=fabric_id, _allow_zero=True)
        if confirm is not True:
            raise ValueError(
                "delete_fabric is destructive; pass confirm=True to proceed. "
                f"Affected: fabric_id={fabric_id}"
            )
        await client.delete(fabric_path(fabric_id))
