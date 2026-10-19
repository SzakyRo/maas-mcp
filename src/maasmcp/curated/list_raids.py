"""list_raids: GET /nodes/{system_id}/raids/."""

from __future__ import annotations

from typing import Annotated, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.storage import Raid
from maasmcp.curated._storage_paths import _validate_ids, raids_path
from maasmcp.maas.client import MaasClient


class ListRaidsTool:
    name = "list_raids"
    description = (
        "List all RAID arrays on a MAAS machine. Use this before "
        "update_raid or delete_raid. Returns a list of RAID dicts "
        "(id, name, level, uuid, ...). "
        "Accepts system_id or hostname (provide exactly one). "
        "Read-only; no confirmation needed."
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
    ) -> list[Raid]:
        system_id = await resolve_system_id(client, system_id, hostname)
        _validate_ids(system_id)
        resp = await client.get(raids_path(system_id))
        return cast(list[Raid], resp) if isinstance(resp, list) else []
