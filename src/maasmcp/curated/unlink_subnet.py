"""unlink_subnet: POST /nodes/{system_id}/interfaces/{id}/op-unlink_subnet."""

from __future__ import annotations

from typing import Annotated, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import _validate_id, _validate_ids, interface_op_path
from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.network import Interface
from maasmcp.maas.client import MaasClient


class UnlinkSubnetTool:
    name = "unlink_subnet"
    description = (
        "Unlink a subnet from a network interface. "
        "Use this after listing interface links to remove an explicit subnet "
        "assignment; for initial subnet linking rely on VLAN assignment or the "
        "interface link/subnet workflow. "
        "MAAS's unlink op identifies the link by its link id (the id under an "
        "interface's links[] from get_interface/list_interfaces) — prefer "
        "link_id. subnet_id is kept as a fallback for older MAAS releases. "
        "Returns the updated interface dict. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        iface_id: Annotated[int, Field(description="MAAS id of the interface to modify.")],
        subnet_id: Annotated[
            int | None,
            Field(description="MAAS id of the subnet to unlink (legacy; prefer link_id)."),
        ] = None,
        link_id: Annotated[
            int | None,
            Field(
                description="Id of the subnet link to remove (interface links[].id). "
                "Required by current MAAS releases."
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
        if link_id is not None:
            _validate_id(link_id=link_id)
        if subnet_id is not None:
            _validate_id(subnet_id=subnet_id)
        if link_id is None and subnet_id is None:
            raise ValueError("unlink_subnet requires link_id (preferred) or subnet_id")
        if confirm is not True:
            raise ValueError(
                "unlink_subnet is destructive; pass confirm=True to proceed. "
                f"Affected: system_id={system_id}, hostname={hostname}, "
                f"iface_id={iface_id}, link_id={link_id}, subnet_id={subnet_id}"
            )
        # MAAS's unlink body param is the LINK id (docs: "ID of the subnet
        # link on the interface to remove"); current releases 400 on a bare
        # subnet id. Keep the subnet form for older releases.
        body = {"id": link_id} if link_id is not None else {"subnet": subnet_id}
        resp = await client.post(
            interface_op_path(system_id, iface_id, "op-unlink_subnet"),
            json=body,
        )
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for unlink_subnet response "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return cast(Interface, resp)
