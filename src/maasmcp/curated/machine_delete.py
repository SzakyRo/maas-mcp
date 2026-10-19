"""machine_delete: DELETE /machines/{system_id}/."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._machine_paths import machine_path, validate_system_id
from maasmcp.curated._resolve import resolve_system_id
from maasmcp.maas.client import MaasClient


class MachineDeleteTool:
    name = "machine_delete"
    description = (
        "Delete a machine in MAAS. "
        "Use this for direct MAAS API access when no curated verb exists; call "
        "get_machine or list_machines to confirm the target first. A machine "
        "that hosts pod virtual machines cannot be deleted unless force=True "
        "(which also removes the hosted pods). "
        "Returns the MAAS response. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        force: Annotated[
            bool,
            Field(
                description="If True, override the 'hosts pod virtual machines' refusal — "
                "the hosted pods are removed as well."
            ),
        ] = False,
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
                "machine_delete is destructive; pass confirm=True to proceed. "
                f"Affected: system_id={system_id}, hostname={hostname}"
            )
        path = machine_path(system_id)
        if force:
            # DELETE takes no body; force travels as a query parameter.
            path = f"{path}?force=1"
        return await client.delete(  # type: ignore[no-any-return]
            path
        )
