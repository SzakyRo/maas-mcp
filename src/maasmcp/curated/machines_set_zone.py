"""machines_set_zone: POST /api/2.0/machines/?op=set_zone."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._machine_paths import machines_op_path
from maasmcp.curated._resolve import resolve_system_id
from maasmcp.maas.client import MaasClient


class MachinesSetZoneTool:
    name = "machines_set_zone"
    description = (
        "Set the zone for a machine in MAAS (POST /machines?op=set_zone). "
        "Accepts system_id (nodes) or hostname (provide exactly one). "
        "Call once per machine. "
        "Returns the MAAS response (HTTP 204 on success). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        zone: Annotated[str, Field(description="The zone name.")],
        *,
        nodes: Annotated[
            str | None,
            Field(
                description="The system_id of the machine to assign to this zone. "
                "Provide this or hostname, exactly one."
            ),
        ] = None,
        hostname: Annotated[
            str | None,
            Field(
                description="Exact hostname; resolved to system_id server-side."
            ),
        ] = None,
        confirm: Annotated[
            bool,
            Field(description="Must be True to proceed. This operation is destructive."),
        ] = False,
    ) -> dict[str, Any] | list[dict[str, Any]] | None:
        # Resolve BEFORE the confirm gate (tree-wide rule T4): addressing
        # errors fail fast without waiting on the operator's confirm.
        nodes = await resolve_system_id(client, nodes, hostname)
        if confirm is not True:
            raise ValueError(
                "machines_set_zone is destructive; pass confirm=True to proceed. "
                f"Affected: zone={zone}, nodes={nodes}, hostname={hostname}"
            )
        params = {k: v for k, v in {"zone": zone, "nodes": nodes}.items() if v is not None}
        return await client.post(  # type: ignore[no-any-return]
            machines_op_path("set_zone"), json=params
        )
