"""create_interface: POST /nodes/{system_id}/interfaces/op-create_physical."""

from __future__ import annotations

from typing import Annotated, Any, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import (
    _validate_id,
    _validate_ids,
    interfaces_collection_op_path,
)
from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.network import Interface
from maasmcp.maas.client import MaasClient


class CreateInterfaceTool:
    name = "create_interface"
    description = (
        "Create a plain physical interface on a MAAS machine "
        "(POST /nodes/{system_id}/interfaces/op-create_physical). "
        "Use this for simple physical/interface records; for bonds, bridges, "
        "or VLAN sub-interfaces use create_bond, create_bridge, or "
        "create_interface_vlan instead. "
        "Returns the newly-created interface dict. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        mac_address: Annotated[
            str,
            Field(
                description="MAC address for the interface (required by MAAS for physical "
                "interfaces, e.g. '52:54:00:12:34:56')."
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
        name: Annotated[str | None, Field(description="Name for the new interface.")] = None,
        vlan: Annotated[int | None, Field(description="MAAS internal VLAN id to assign.")] = None,
        tags: Annotated[
            list[str] | None, Field(description="Tags to attach to the interface.")
        ] = None,
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> Interface:
        system_id = await resolve_system_id(client, system_id, hostname)
        _validate_ids(system_id)
        if vlan is not None:
            _validate_id(vlan=vlan)
        if confirm is not True:
            raise ValueError(
                "create_interface is destructive; pass confirm=True to proceed. "
                f"Affected: system_id={system_id}, hostname={hostname}, "
                f"mac_address={mac_address}"
            )
        body: dict[str, Any] = {"mac_address": mac_address}
        if name is not None:
            body["name"] = name
        if vlan is not None:
            body["vlan"] = vlan
        if tags is not None:
            body["tags"] = tags
        resp = await client.post(
            interfaces_collection_op_path(system_id, "op-create_physical"), json=body
        )
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for created interface "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return cast(Interface, resp)
