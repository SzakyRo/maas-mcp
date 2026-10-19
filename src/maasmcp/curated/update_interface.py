"""update_interface: PUT /nodes/{system_id}/interfaces/{id}/.

Wraps the MAAS interface-update endpoint so callers can set admin-state
fields (``link_connected``, ``link_speed``, ``interface_speed``), rename
the interface, change MAC, edit tags, or set/clear the untagged VLAN
without dropping to the raw ``MaasClient``.

Per MAAS 3.7.2 quirks (discovered 2026-07-09 on awake-bear):
- ``vlan: null`` returns HTTP 400 ("Select a valid choice"). To CLEAR the
  untagged VLAN, use ``vid=""`` (empty string).
- Pass ``vid`` as the IEEE 802.1Q VID (e.g. 79); the tool translates to
  MAAS's internal VLAN primary key before sending — same convention as
  :class:`AssignVlanToInterfaceTool`.

This is the verb that the LACP-bonding workflow relies on: pre-marking
member NICs as 10G/connected before ``create_bond`` so MAAS classifies
the bond correctly post-create (see
``maas-bond-slave-suppression`` memory).
"""

from __future__ import annotations

from typing import Annotated, Any, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import (
    _resolve_vlan_id,
    _validate_id,
    _validate_ids,
    interface_path,
)
from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.network import Interface
from maasmcp.maas.client import MaasClient


class UpdateInterfaceTool:
    name = "update_interface"
    description = (
        "Update a physical interface's admin state (link_connected, link_speed, "
        "interface_speed), name, MAC, tags, mtu, accept_ra, or untagged VLAN "
        "(IEEE 802.1Q VID, or '' to clear — MAAS rejects null). "
        "Use this after create_interface or to adjust an existing NIC; pre-mark "
        "LACP bond members as 10G/connected before create_bond. "
        "MAAS restricts edits on Deployed machines to name and mac_address only; "
        "Ready/Broken machines accept all fields. Bond/bridge tuning params "
        "(bond_mode, bond_miimon, bridge_stp, …) are set at creation time via "
        "create_bond. "
        "Returns the updated interface dict. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        iface_id: Annotated[int, Field(description="MAAS id of the interface to update.")],
        link_connected: Annotated[
            bool | None, Field(description="Administrative link-connected state.")
        ] = None,
        link_speed: Annotated[
            int | None,
            Field(description="Link speed in Mbps (e.g. 10000 for 10G)."),
        ] = None,
        interface_speed: Annotated[
            int | None,
            Field(description="Physical interface speed in Mbps (e.g. 10000 for 10G)."),
        ] = None,
        name: Annotated[str | None, Field(description="New interface name.")] = None,
        mac_address: Annotated[str | None, Field(description="New MAC address.")] = None,
        tags: Annotated[
            list[str] | None, Field(description="List of tag strings to set on the interface.")
        ] = None,
        mtu: Annotated[
            int | None, Field(description="MTU for the interface (e.g. 9000 for jumbo frames).")
        ] = None,
        accept_ra: Annotated[
            bool | None,
            Field(description="Accept router advertisements (IPv6)."),
        ] = None,
        vid: Annotated[
            int | str | None,
            Field(
                description=(
                    "IEEE 802.1Q VID (e.g. 79) to assign, or an empty string '' "
                    "to clear the untagged VLAN."
                )
            ),
        ] = None,
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
            bool,
            Field(description="Must be True to proceed. This operation is destructive."),
        ] = False,
    ) -> Interface:
        system_id = await resolve_system_id(client, system_id, hostname)
        _validate_ids(system_id, iface_id=iface_id)
        if confirm is not True:
            raise ValueError(
                "update_interface is destructive; pass confirm=True to proceed. "
                f"Affected: system_id={system_id}, hostname={hostname}, "
                f"iface_id={iface_id}"
            )

        body: dict[str, Any] = {}
        if link_connected is not None:
            body["link_connected"] = bool(link_connected)
        if link_speed is not None:
            _validate_id(link_speed=link_speed)
            body["link_speed"] = int(link_speed)
        if interface_speed is not None:
            _validate_id(interface_speed=interface_speed)
            body["interface_speed"] = int(interface_speed)
        if name is not None:
            body["name"] = name
        if mac_address is not None:
            body["mac_address"] = mac_address
        if tags is not None:
            body["tags"] = tags
        if mtu is not None:
            body["mtu"] = int(mtu)
        if accept_ra is not None:
            body["accept_ra"] = bool(accept_ra)
        if vid is not None:
            # Two wire shapes:
            #   - empty string "" → clear untagged VLAN (MAAS rejects null)
            #   - integer VID     → translate to MAAS internal id
            if isinstance(vid, str):
                if vid != "":
                    raise ValueError(
                        "vid must be an integer (IEEE 802.1Q VID) or the "
                        'empty string "" (to clear). Got: '
                        f"{vid!r}"
                    )
                body["vlan"] = ""  # MAAS quirk: clears the untagged VLAN
            else:
                _validate_id(vid=vid)
                body["vlan"] = await _resolve_vlan_id(client, vid)

        if not body:
            raise ValueError(
                "update_interface requires at least one field to change; "
                "all update parameters are None."
            )

        resp = await client.put(interface_path(system_id, iface_id), json=body)
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for updated interface "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return cast(Interface, resp)
