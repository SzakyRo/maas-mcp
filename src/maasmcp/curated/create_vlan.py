"""create_vlan: POST /api/2.0/fabrics/{fabric_id}/vlans/."""

from __future__ import annotations

from typing import Annotated, Any, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import _validate_id, vlans_path
from maasmcp.curated._schemas.network import Vlan
from maasmcp.maas.client import MaasClient


class CreateVlanTool:
    name = "create_vlan"
    description = (
        "Create a VLAN on a specific fabric (POST /fabrics/{fabric_id}/vlans/). "
        "Use this for fabric-scoped VLAN management; for a VLAN sub-interface on "
        "a machine NIC use create_interface_vlan instead. "
        "Returns the newly-created VLAN dict. "
        "State-mutating — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        vid: Annotated[int, Field(description="IEEE 802.1Q VLAN identifier (1-4094).")],
        fabric_id: Annotated[int, Field(description="MAAS id of the fabric that owns the VLAN.")],
        name: Annotated[
            str | None, Field(description="Optional display name for the VLAN.")
        ] = None,
        description: Annotated[
            str | None, Field(description="Optional human-readable description.")
        ] = None,
        mtu: Annotated[
            int | None, Field(description="MTU to use on the VLAN (e.g. 9000 for jumbo frames).")
        ] = None,
        space: Annotated[
            str | None, Field(description="Name or id of the space this VLAN should be placed in.")
        ] = None,
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> Vlan:
        if not 1 <= vid <= 4094:
            raise ValueError(f"vlan vid must be in 1..4094 (got {vid})")
        _validate_id(fabric_id=fabric_id, _allow_zero=True)
        if confirm is not True:
            raise ValueError(
                "create_vlan is destructive; pass confirm=True to proceed. "
                f"Affected: vid={vid}, fabric_id={fabric_id}"
            )
        # The fabric is already in the URL (vlans_path is fabric-scoped); the
        # MAAS VlansHandler body spec is name/description/vid/mtu/space —
        # sending a duplicate `fabric` field is off-spec.
        body: dict[str, Any] = {"vid": vid}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if mtu is not None:
            body["mtu"] = mtu
        if space is not None:
            body["space"] = space
        resp = await client.post(vlans_path(fabric_id), json=body)
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for created vlan "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return cast(Vlan, resp)
