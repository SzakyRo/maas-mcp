"""create_interface_vlan: POST /nodes/{system_id}/interfaces/op-create_vlan.

Collection-level endpoint (MAAS does not accept the parent iface id as a
path segment). Parent id goes in the body field ``parent``; the VLAN is
identified by its MAAS internal primary key (we accept the IEEE 802.1Q
VID from the caller and translate it via list_subnets).

NOTE: This is the nested interface-scoped variant of create_vlan (which lives
under /vlans/ at the cluster level). The verb names are intentionally distinct.
"""

from __future__ import annotations

from typing import Annotated, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import (
    _resolve_vlan_id,
    _validate_id,
    _validate_ids,
    interface_path,
    interfaces_collection_op_path,
)
from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.network import Interface
from maasmcp.maas.client import MaasClient


class CreateInterfaceVlanTool:
    name = "create_interface_vlan"
    description = (
        "Create a child VLAN interface on a parent interface "
        "(op-create_vlan; body 'parent'=parent iface id, 'vlan'=translated from "
        "the IEEE 802.1Q VID you pass). Use this after you know the parent "
        "interface id and VID; for cluster-level VLAN creation use create_vlan. "
        "NOTE: MAAS 500s if the parent's untagged VLAN differs from the target, "
        "so this tool first PUTs the parent's untagged VLAN to the given VID — "
        "the parent's VLAN assignment will change. "
        "Returns the newly-created VLAN interface dict. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        parent_id: Annotated[int, Field(description="MAAS id of the parent interface.")],
        vid: Annotated[
            int,
            Field(description="IEEE 802.1Q VID (e.g. 79); translated to MAAS's internal VLAN id."),
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
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> Interface:
        system_id = await resolve_system_id(client, system_id, hostname)
        _validate_ids(system_id, parent_id=parent_id)
        _validate_id(vid=vid)
        if confirm is not True:
            raise ValueError(
                "create_interface_vlan is destructive; pass confirm=True to proceed. "
                f"Affected: system_id={system_id}, hostname={hostname}, "
                f"parent_id={parent_id}, vid={vid}"
            )
        # MAAS's body field `vlan` is the internal primary key, not the IEEE VID.
        maas_vlan_id = await _resolve_vlan_id(client, vid)
        # Pre-condition auto-fix: op-create_vlan 500s when the parent's untagged
        # VLAN is unset/different. Set it idempotently before posting the op.
        # This is transparent to callers — they see the same end state.
        await client.put(
            interface_path(system_id, parent_id),
            json={"vlan": maas_vlan_id},
        )
        resp = await client.post(
            interfaces_collection_op_path(system_id, "op-create_vlan"),
            json={"parent": parent_id, "vlan": maas_vlan_id},
        )
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for created interface_vlan "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return cast(Interface, resp)
