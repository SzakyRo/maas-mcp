"""list_interfaces: GET /nodes/{system_id}/interfaces/."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import _validate_ids, interfaces_path
from maasmcp.curated._resolve import resolve_system_id
from maasmcp.maas.client import MaasClient


class ListInterfacesTool:
    name = "list_interfaces"
    description = (
        "List all network interfaces on a MAAS machine. Use this before "
        "get_interface or assign_vlan_to_interface. Returns a list of "
        "interface dicts. Accepts system_id or hostname (provide exactly "
        "one). Read-only; no confirmation needed."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        system_id: Annotated[
            str | None,
            Field(
                description="MAAS system_id of the machine. "
                "Provide this or hostname, exactly one."
            ),
        ] = None,
        *,
        hostname: Annotated[
            str | None,
            Field(description="Exact hostname of the machine; resolved to system_id server-side."),
        ] = None,
    ) -> list[dict[str, Any]]:
        system_id = await resolve_system_id(client, system_id, hostname)
        _validate_ids(system_id)
        resp = await client.get(interfaces_path(system_id))
        if isinstance(resp, dict) and "interfaces" in resp:
            return list(resp["interfaces"])
        if isinstance(resp, list):
            return resp
        return []
