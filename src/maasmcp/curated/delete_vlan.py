"""delete_vlan: DELETE /fabrics/{fabric_id}/vlans/{vid}/.

The ``vid`` parameter is the IEEE 802.1Q VLAN identifier (e.g. 79).
MAAS's VLAN endpoints are fabric-scoped — both fabric_id and vid are
required to build the URL.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import _validate_id, vlan_path
from maasmcp.maas.client import MaasClient


class DeleteVlanTool:
    name = "delete_vlan"
    description = (
        "Delete a VLAN identified by fabric_id and vid. "
        "Use this only after deleting or moving all subnets and interfaces on "
        "the VLAN (see delete_subnet and list_vlans). "
        "Returns nothing on success. "
        "DESTRUCTIVE (cluster-wide, affects every interface on the VLAN) — "
        "must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        fabric_id: Annotated[int, Field(description="MAAS id of the fabric that owns the VLAN.")],
        vid: Annotated[int, Field(description="IEEE 802.1Q VLAN ID (vid) to delete.")],
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> None:
        _validate_id(fabric_id=fabric_id, _allow_zero=True)
        if confirm is not True:
            raise ValueError(
                "delete_vlan is destructive; pass confirm=True to proceed. "
                f"Affected: fabric_id={fabric_id}, vid={vid}"
            )
        await client.delete(vlan_path(fabric_id, vid))
