"""get_interface: GET /nodes/{system_id}/interfaces/{id}/."""

from __future__ import annotations

from typing import Annotated, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import _validate_ids, interface_path
from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.network import Interface
from maasmcp.maas.client import MaasClient


class GetInterfaceTool:
    name = "get_interface"
    description = (
        "Fetch one network interface. "
        "Use this after list_interfaces to inspect a specific interface. "
        "Returns the full MAAS interface dict. "
        "Accepts system_id or hostname (provide exactly one). "
        "Read-only; no confirmation needed."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        iface_id: Annotated[int, Field(description="MAAS id of the interface to fetch.")],
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
    ) -> Interface:
        system_id = await resolve_system_id(client, system_id, hostname)
        _validate_ids(system_id, iface_id=iface_id)
        resp = await client.get(interface_path(system_id, iface_id))
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for interface {iface_id} "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return cast(Interface, resp)
