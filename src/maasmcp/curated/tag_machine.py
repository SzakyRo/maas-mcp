"""tag_machine: add a tag to a machine (by hostname OR system_id)."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._storage_paths import quote_segment
from maasmcp.maas.client import MaasClient


class TagMachineTool:
    name = "tag_machine"
    description = (
        "Add a tag to a machine identified by hostname or system_id. "
        "Use when grouping or selecting machines by tag; the resolver turns "
        "hostname into a system_id before applying the tag. "
        "Returns the MAAS tag update response dict. "
        "State-mutating — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        tag: Annotated[
            str,
            Field(description="Tag name to add to the machine."),
        ],
        *,
        hostname: Annotated[
            str | None,
            Field(
                description="Exact hostname of the machine to tag. "
                "Provide this or system_id, exactly one."
            ),
        ] = None,
        system_id: Annotated[
            str | None,
            Field(
                description="MAAS system_id of the machine to tag. "
                "Provide this or hostname, exactly one."
            ),
        ] = None,
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation mutates state.")
        ] = False,
    ) -> dict[str, Any] | None:
        # Resolve BEFORE the confirm gate (tree-wide rule T4): addressing
        # errors fail fast without waiting on the operator's confirm.
        system_id = await resolve_system_id(client, system_id, hostname)
        if confirm is not True:
            raise ValueError(
                "tag_machine mutates machine state; pass confirm=True to proceed. "
                f"Affected: hostname={hostname}, system_id={system_id}, tag={tag!r}"
            )
        return await client.post(  # type: ignore[no-any-return]
            f"/api/2.0/tags/{quote_segment(tag)}/op-update_nodes",
            json={"add": system_id},
        )
