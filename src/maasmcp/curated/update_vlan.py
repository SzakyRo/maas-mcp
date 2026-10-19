"""update_vlan: PUT /fabrics/{fabric_id}/vlans/{vid}/.

The ``vid`` parameter is the IEEE 802.1Q VLAN identifier (e.g. 79).
MAAS's VLAN endpoints are fabric-scoped — both fabric_id and vid are
required to build the URL. vid 0 is the fabric's built-in untagged default
VLAN (the target when enabling MAAS-managed DHCP via primary_rack).
"""

from __future__ import annotations

from typing import Annotated, Any, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import _validate_id, vlan_path
from maasmcp.curated._schemas.network import Vlan
from maasmcp.maas.client import MaasClient


class UpdateVlanTool:
    name = "update_vlan"
    description = (
        "Update a VLAN on a fabric: name, description, mtu, dhcp_on, "
        "primary_rack/secondary_rack (rack controller system_ids — the standard "
        "way to enable MAAS-managed DHCP is vid 0 with a primary_rack), relay_vlan, "
        "or space. vid itself is immutable. Identify the target by fabric_id and "
        "vid (the untagged default VLAN is vid 0). "
        "Returns the updated VLAN dict (keys include id, vid, name, description, "
        "fabric_id, mtu, dhcp_on, and primary_rack). "
        "DESTRUCTIVE (cluster-wide) — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        fabric_id: Annotated[int, Field(description="MAAS id of the fabric that owns the VLAN.")],
        vid: Annotated[
            int,
            Field(
                description="IEEE 802.1Q VLAN ID (vid) of the VLAN to update; 0 is the "
                "fabric's untagged default VLAN."
            ),
        ],
        name: Annotated[
            str | None,
            Field(description="New name for the VLAN. Leave unset to keep the current name."),
        ] = None,
        description: Annotated[
            str | None,
            Field(
                description="New description for the VLAN. Leave unset to keep the current description."
            ),
        ] = None,
        mtu: Annotated[
            int | None, Field(description="MTU for the VLAN. Leave unset to keep the current MTU.")
        ] = None,
        dhcp_on: Annotated[
            bool | None,
            Field(
                description="True to manage DHCP on this VLAN through MAAS (requires primary_rack "
                "to be set). Leave unset to keep the current setting."
            ),
        ] = None,
        primary_rack: Annotated[
            str | None,
            Field(
                description="system_id of the primary rack controller managing the VLAN "
                "(enables MAAS-managed DHCP). Pass an empty string to clear."
            ),
        ] = None,
        secondary_rack: Annotated[
            str | None,
            Field(
                description="system_id of the secondary rack controller for DHCP failover. "
                "Pass an empty string to clear."
            ),
        ] = None,
        relay_vlan: Annotated[
            int | None,
            Field(
                description="Internal id of a VLAN to relay DHCP requests through (used instead "
                "of, not together with, rack controllers). Its dhcp_on must be true."
            ),
        ] = None,
        space: Annotated[
            str | None,
            Field(
                description="Name or id of the space to move the VLAN into; pass an empty string "
                "to place it in the 'undefined' space."
            ),
        ] = None,
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> Vlan:
        _validate_id(fabric_id=fabric_id, _allow_zero=True)
        if confirm is not True:
            raise ValueError(
                "update_vlan is destructive; pass confirm=True to proceed. "
                f"Affected: fabric_id={fabric_id}, vid={vid}"
            )
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if mtu is not None:
            body["mtu"] = mtu
        if dhcp_on is not None:
            body["dhcp_on"] = dhcp_on
        if primary_rack is not None:
            body["primary_rack"] = primary_rack
        if secondary_rack is not None:
            body["secondary_rack"] = secondary_rack
        if relay_vlan is not None:
            body["relay_vlan"] = relay_vlan
        if space is not None:
            body["space"] = space
        if not body:
            raise ValueError("update_vlan: nothing to update — pass at least one field to change.")
        resp = await client.put(vlan_path(fabric_id, vid), json=body)
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for updated vlan "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return cast(Vlan, resp)
