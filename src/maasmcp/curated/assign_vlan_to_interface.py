"""assign_vlan_to_interface: PUT /nodes/{system_id}/interfaces/{id}/ with vlan body.

Accepts the IEEE 802.1Q VID (e.g. 79) and translates it to MAAS's internal
VLAN primary key (e.g. 5001) before sending. MAAS's body field expects the
internal id, not the IEEE VID — confirmed by live PUT against MAAS 3.7.2
(returns 400 "Select a valid choice" when given the VID).
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import (
    _resolve_vlan_id,
    _validate_id,
    _validate_ids,
    interface_path,
)
from maasmcp.curated._resolve import resolve_system_id
from maasmcp.maas.client import MaasClient


class AssignVlanToInterfaceTool:
    name = "assign_vlan_to_interface"
    description = (
        "Assign a VLAN to a network interface using the IEEE 802.1Q VID. "
        "Use this on each bond member before create_bond, or to move an "
        "interface to a different VLAN; the VID is translated to MAAS's "
        "internal VLAN id internally. "
        "Returns the updated interface dict. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        iface_id: Annotated[int, Field(description="MAAS interface id to assign the VLAN to.")],
        vid: Annotated[int, Field(description="IEEE 802.1Q VLAN ID (vid) to assign.")],
        *,
        system_id: Annotated[
            str | None,
            Field(
                description="MAAS system_id of the machine. "
                "Provide this or hostname, exactly one."
            ),
        ] = None,
        hostname: Annotated[
            str | None,
            Field(description="Exact hostname of the machine; resolved to system_id server-side."),
        ] = None,
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> dict[str, Any]:
        system_id = await resolve_system_id(client, system_id, hostname)
        _validate_ids(system_id, iface_id=iface_id)
        _validate_id(vid=vid)
        if confirm is not True:
            raise ValueError(
                "assign_vlan_to_interface is destructive; pass confirm=True. "
                f"Affected: system_id={system_id}, hostname={hostname}, "
                f"iface_id={iface_id}, vid={vid}"
            )
        maas_vlan_id = await _resolve_vlan_id(client, vid)
        resp = await client.put(
            interface_path(system_id, iface_id),
            json={"vlan": maas_vlan_id},
        )
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for updated interface "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return resp
