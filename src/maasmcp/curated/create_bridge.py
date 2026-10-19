"""create_bridge: POST /nodes/{system_id}/interfaces/op-create_bridge.

MAAS exposes create_bridge at the **collection** level, not nested under a
parent interface id. Per the MAAS API doc the body field is the singular
``parent`` (one parent interface id); the plural ``parents`` is for bonds.
"""

from __future__ import annotations

from typing import Annotated, Any, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_helpers import (
    classify_link_states,
    probe_link_states,
)
from maasmcp.curated._network_paths import (
    _resolve_vlan_id,
    _validate_id,
    _validate_ids,
    interfaces_collection_op_path,
)
from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.network import BridgeInterface
from maasmcp.maas.client import MaasClient


class CreateBridgeTool:
    name = "create_bridge"
    description = (
        "Create a bridge interface on a MAAS machine (POST op-create_bridge). "
        "MAAS takes a single parent interface id, not a member list: pass "
        "exactly one member. Use this instead of create_interface when "
        "aggregating an existing interface into a bridge; list candidate "
        "parents with list_interfaces first. "
        "Returns the newly-created bridge dict augmented with "
        "'link_state_classification' and 'member_link_states'. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        name: Annotated[str, Field(description="Name for the new bridge interface.")],
        members: Annotated[
            list[int],
            Field(
                description="MAAS ids of the member interfaces to enslave. MAAS's bridge model "
                "takes a single parent — pass exactly one id."
            ),
        ],
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
        vid: Annotated[
            int | None,
            Field(
                description="IEEE 802.1Q VLAN ID (vid) to assign to the bridge (1..4094) — "
                "same convention as assign_vlan_to_interface; translated to MAAS's internal "
                "VLAN id before sending."
            ),
        ] = None,
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> BridgeInterface:
        system_id = await resolve_system_id(client, system_id, hostname)
        _validate_ids(system_id)
        if not members:
            raise ValueError("create_bridge requires at least one member interface id")
        if len(members) > 1:
            raise ValueError(
                "create_bridge takes a single parent interface per the MAAS API "
                "(body field 'parent'); pass exactly one member id. Got "
                f"{members}. Create a bond first if you need LACP/multiple NICs."
            )
        if vid is not None:
            _validate_id(vid=vid)
        if confirm is not True:
            raise ValueError(
                "create_bridge is destructive; pass confirm=True to proceed. "
                f"Affected: system_id={system_id}, hostname={hostname}, "
                f"members={members}"
            )
        body: dict[str, Any] = {
            "name": name,
            "parent": members[0],
        }
        if vid is not None:
            # Same VID convention as assign_vlan_to_interface.
            body["vlan"] = await _resolve_vlan_id(client, vid)
        resp = await client.post(
            interfaces_collection_op_path(system_id, "op-create_bridge"),
            json=body,
        )
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for created bridge "
                f"(got {type(resp).__name__}); schema drift?"
            )
        # Post-create link-state probe: re-read the bridge and its member.
        # Never raise — the create succeeded; a probe failure just classifies
        # the result as 'unknown'.
        parent_id = resp.get("id")
        # parent_id is absent; MAAS response is already a valid interface
        # record, so return it as-is.
        if not isinstance(parent_id, int):
            return cast(BridgeInterface, resp)
        link_states, _errors = await probe_link_states(
            client,
            system_id,
            parent_id=parent_id,
            member_ids=members,
        )
        member_link_states = [
            {
                "id": m.get("id"),
                "name": m.get("name"),
                "link_connected": bool(m.get("link_connected")),
            }
            for m in link_states.get("members") or []
            if isinstance(m, dict)
        ]
        return cast(
            BridgeInterface,
            {
                **resp,
                "link_state_classification": classify_link_states(link_states),
                "member_link_states": member_link_states,
            },
        )
