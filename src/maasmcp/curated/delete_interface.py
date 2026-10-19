"""delete_interface: DELETE /nodes/{system_id}/interfaces/{id}/."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import _validate_ids, interface_path
from maasmcp.curated._resolve import resolve_system_id
from maasmcp.maas.client import MaasClient


class DeleteInterfaceTool:
    name = "delete_interface"
    description = (
        "Delete a network interface from a MAAS machine. "
        "Use this to remove a physical, VLAN, bond, or bridge interface; first "
        "unlink any subnets with unlink_subnet. "
        "Returns nothing on success. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        iface_id: Annotated[int, Field(description="MAAS id of the interface to delete.")],
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
    ) -> None:
        system_id = await resolve_system_id(client, system_id, hostname)
        _validate_ids(system_id, iface_id=iface_id)
        if confirm is not True:
            raise ValueError(
                "delete_interface is destructive; pass confirm=True to proceed. "
                f"Affected: system_id={system_id}, hostname={hostname}, "
                f"iface_id={iface_id}"
            )
        await client.delete(interface_path(system_id, iface_id))
