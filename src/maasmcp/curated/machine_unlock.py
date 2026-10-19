"""machine_unlock: POST /api/2.0/machines/{system_id}/?op=unlock."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._machine_paths import machine_query_op_path, validate_system_id
from maasmcp.curated._resolve import resolve_system_id
from maasmcp.maas.client import MaasClient


class MachineUnlockTool:
    name = "machine_unlock"
    description = (
        "Unlock a machine in MAAS so it can be acted upon again. "
        "Use this for direct MAAS API access when no curated verb covers it; "
        "see also machine_lock. "
        "Returns the MAAS response. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        comment: Annotated[
            str | None,
            Field(description="Optional comment for the event log."),
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
                "machine_unlock is destructive; pass confirm=True to proceed. "
                f"Affected: system_id={system_id}, hostname={hostname}, comment={comment}"
            )
        path = machine_query_op_path(system_id, "unlock")
        params = {k: v for k, v in {"comment": comment}.items() if v is not None}
        return await client.post(path, json=params)  # type: ignore[no-any-return]
