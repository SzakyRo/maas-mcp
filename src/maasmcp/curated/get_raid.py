"""get_raid: GET /nodes/{system_id}/raid/{id}/."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.storage import Raid
from maasmcp.curated._storage_paths import _validate_ids, raid_path
from maasmcp.maas.client import MaasClient


class GetRaidTool:
    name = "get_raid"
    description = (
        "Fetch one RAID array on a machine by its numeric id. "
        "Use this after list_raids to discover the raid_id. "
        "Returns the MAAS RAID dict (id, name, level, devices/spares, size, etc.). "
        "Accepts system_id or hostname (provide exactly one). "
        "Read-only; no confirmation needed."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        raid_id: Annotated[int, Field(description="MAAS id of the RAID array.")],
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
    ) -> Raid:
        system_id = await resolve_system_id(client, system_id, hostname)
        _validate_ids(system_id, raid_id=raid_id)
        resp: Raid = await client.get(raid_path(system_id, raid_id))
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for raid {raid_id} "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return resp
