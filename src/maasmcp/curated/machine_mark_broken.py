"""machine_mark_broken: POST /api/2.0/machines/{system_id}/?op=mark_broken."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._machine_paths import machine_query_op_path, validate_system_id
from maasmcp.curated._resolve import resolve_system_id
from maasmcp.maas.client import MaasClient


class MachineMarkBrokenTool:
    name = "machine_mark_broken"
    description = (
        "Mark a machine as broken in MAAS. "
        "Use this for direct MAAS API access when no curated verb covers it; "
        "see also machine_mark_fixed. "
        "Returns the MAAS response. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        comment: Annotated[
            str | None,
            Field(
                description="Optional comment for the event log. Will be displayed "
                "on the node as an error description until marked fixed."
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
    ) -> dict[str, Any] | list[dict[str, Any]] | None:
        system_id = await resolve_system_id(client, system_id, hostname)
        validate_system_id(system_id)
        if confirm is not True:
            raise ValueError(
                "machine_mark_broken is destructive; pass confirm=True to proceed. "
                f"Affected: system_id={system_id}, hostname={hostname}, comment={comment}"
            )
        path = machine_query_op_path(system_id, "mark_broken")
        params = {k: v for k, v in {"comment": comment}.items() if v is not None}
        return await client.post(path, json=params)  # type: ignore[no-any-return]
