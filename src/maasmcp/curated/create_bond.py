"""create_bond: POST /nodes/{system_id}/interfaces/op-create_bond.

MAAS exposes create_bond at the **collection** level, not nested under a
parent interface id. Members (parent interface ids) are repeated multipart
parts under the ``parents`` key.
"""

from __future__ import annotations

from typing import Annotated, Any, cast

import structlog
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
    interface_path,
    interfaces_collection_op_path,
)
from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.network import BondInterface
from maasmcp.maas.client import MaasClient

_log = structlog.get_logger(__name__)


class CreateBondTool:
    name = "create_bond"
    description = (
        "Create a bond interface on a MAAS machine from member interface ids "
        "(op-create_bond, body 'parents'). "
        "Use this after assigning all members to the same VLAN with "
        "assign_vlan_to_interface. NOTE: before creating the bond, this tool also "
        "PUTs link_connected=True, link_speed=10000, interface_speed=10000 on each "
        "member (best-effort pre-marking so MAAS classifies the bond correctly) — "
        "it mutates the member interfaces even if bond creation then fails. "
        "bond_mode is passed through to MAAS (e.g. '802.3ad', 'active-backup'); "
        "if omitted, MAAS applies its default (active-backup). The optional vid "
        "param takes the IEEE 802.1Q VID — same convention as "
        "assign_vlan_to_interface. "
        "Returns the newly-created bond dict augmented with "
        "link_state_classification and member_link_states so you can distinguish "
        "LACP slave-suppression from real physical-layer faults. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        name: Annotated[str, Field(description="Name for the new bond interface.")],
        members: Annotated[
            list[int], Field(description="List of member interface ids to include in the bond.")
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
        bond_mode: Annotated[
            str | None,
            Field(
                description="Bond mode passed to MAAS (e.g. '802.3ad', 'active-backup'). "
                "If omitted, MAAS defaults to active-backup."
            ),
        ] = None,
        bond_downdelay: Annotated[
            int | None, Field(description="Time to disable slave after link failure (ms).")
        ] = None,
        bond_lacp_rate: Annotated[
            str | None, Field(description="LACPDU rate option ('slow' or 'fast').")
        ] = None,
        bond_miimon: Annotated[int | None, Field(description="Link check frequency in ms.")] = None,
        bond_updelay: Annotated[
            int | None, Field(description="Time to enable slave after link recovery (ms).")
        ] = None,
        bond_xmit_hash_policy: Annotated[
            str | None,
            Field(description="Transmit hash policy (e.g. 'layer2', 'layer3+4', 'layer2+3')."),
        ] = None,
        bond_num_grat_arp: Annotated[
            int | None, Field(description="Number of gratuitous ARPs after a failover.")
        ] = None,
        mac_address: Annotated[
            str | None,
            Field(description="MAC address for the bond (defaults to the first member's MAC)."),
        ] = None,
        mtu: Annotated[int | None, Field(description="Bond MTU (e.g. 9000).")] = None,
        accept_ra: Annotated[
            bool | None,
            Field(description="Accept router advertisements (IPv6). If omitted, MAAS default."),
        ] = None,
        tags: Annotated[list[str] | None, Field(description="Tags to attach to the bond.")] = None,
        vid: Annotated[
            int | None,
            Field(
                description="IEEE 802.1Q VLAN ID (vid) for the bond (1..4094); members should "
                "already be on this VLAN. Translated to MAAS's internal VLAN id before sending."
            ),
        ] = None,
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> BondInterface:
        system_id = await resolve_system_id(client, system_id, hostname)
        _validate_ids(system_id)
        if not members:
            raise ValueError("create_bond requires at least one member interface id")
        if vid is not None:
            _validate_id(vid=vid)
        if confirm is not True:
            raise ValueError(
                "create_bond is destructive; pass confirm=True to proceed. "
                f"Affected: system_id={system_id}, hostname={hostname}, "
                f"members={members}"
            )
        body: dict[str, Any] = {
            "name": name,
            "parents": members,
        }
        if bond_mode is not None:
            body["bond_mode"] = bond_mode
        if bond_downdelay is not None:
            body["bond_downdelay"] = bond_downdelay
        if bond_lacp_rate is not None:
            body["bond_lacp_rate"] = bond_lacp_rate
        if bond_miimon is not None:
            body["bond_miimon"] = bond_miimon
        if bond_updelay is not None:
            body["bond_updelay"] = bond_updelay
        if bond_xmit_hash_policy is not None:
            body["bond_xmit_hash_policy"] = bond_xmit_hash_policy
        if bond_num_grat_arp is not None:
            body["bond_num_grat_arp"] = bond_num_grat_arp
        if mac_address is not None:
            body["mac_address"] = mac_address
        if mtu is not None:
            body["mtu"] = mtu
        if accept_ra is not None:
            body["accept_ra"] = accept_ra
        if tags is not None:
            body["tags"] = tags
        if vid is not None:
            # Same VID convention as assign_vlan_to_interface: callers pass the
            # IEEE VID (79); MAAS's interface body wants the internal primary
            # key (5001) — translate via list_subnets lookup.
            body["vlan"] = await _resolve_vlan_id(client, vid)
        # Pre-mark each member as 10G/connected so MAAS classifies the bond
        # correctly post-create. Best-effort: if a PUT fails (e.g. MAAS
        # rejects the override on a deployed machine), we still attempt the
        # bond — slave suppression is the expected LACP behavior regardless.
        # Use interface_path (singular iface id) — interface_op_path would
        # append an op suffix we don't want.
        for member_id in members:
            try:
                await client.put(
                    interface_path(system_id, member_id),
                    json={
                        "link_connected": True,
                        "link_speed": 10000,
                        "interface_speed": 10000,
                    },
                )
            except Exception as exc:
                # Pre-mark is best-effort: bond creation is the goal. But
                # surface the failure — silent pre-mark skips leave the
                # member's link_connected=false and the bond classifier
                # reports bond_down_members_mixed instead of bond_up_members_down.
                _log.warning(
                    "create_bond_pre_mark_failed",
                    system_id=system_id,
                    iface_id=member_id,
                    error=type(exc).__name__,
                    detail=str(exc)[:200],
                )
        resp = await client.post(
            interfaces_collection_op_path(system_id, "op-create_bond"),
            json=body,
        )
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for created bond "
                f"(got {type(resp).__name__}); schema drift?"
            )
        # Post-create link-state probe: re-read the bond and its members so the
        # caller can distinguish LACP slave-suppression (bond up, members down)
        # from a real physical-layer fault. Never raise — the create succeeded;
        # a probe failure just classifies the result as 'unknown'.
        parent_id = resp.get("id")
        # parent_id is absent; MAAS response is already a valid interface
        # record, so return it as-is.
        if not isinstance(parent_id, int):
            return cast(BondInterface, resp)
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
            BondInterface,
            {
                **resp,
                "link_state_classification": classify_link_states(link_states),
                "member_link_states": member_link_states,
            },
        )
