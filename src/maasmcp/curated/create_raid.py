"""create_raid: POST /nodes/{system_id}/raids/.

MAAS accepts ``level`` only as a string enum (``raid-0``..``raid-10``).
The public verb accepts the integer for ergonomics and translates at the
wire boundary.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.storage import Raid
from maasmcp.curated._storage_paths import _validate_ids, raids_path
from maasmcp.maas.client import MaasClient

# MAAS RAID-level enum values, as required by the raids/ POST body. Numeric
# levels are accepted at the public verb boundary and translated here.
_RAID_LEVEL_TO_MAAS = {
    0: "raid-0",
    1: "raid-1",
    5: "raid-5",
    6: "raid-6",
    10: "raid-10",
}


class CreateRaidTool:
    name = "create_raid"
    description = (
        "Create a RAID array on a MAAS machine. "
        "Use this after identifying block devices or partitions; pass active "
        "members via block_devices/partitions (raw, unformatted members are "
        "fine — MAAS marks them as raid members automatically) and optional "
        "spares via spare_devices/spare_partitions. "
        "Returns the newly-created RAID dict. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        level: Annotated[int, Field(description="RAID level: 0, 1, 5, 6, or 10.")],
        *,
        system_id: Annotated[
            str | None,
            Field(
                description="MAAS system_id of the machine. "
                "Provide this or hostname, exactly one."
            ),
        ] = None,
        name: Annotated[str | None, Field(description="Optional name for the RAID array.")] = None,
        uuid: Annotated[str | None, Field(description="Optional UUID for the RAID array.")] = None,
        block_devices: Annotated[
            list[int] | None, Field(description="MAAS ids of active block devices in the array.")
        ] = None,
        partitions: Annotated[
            list[int] | None, Field(description="MAAS ids of active partitions in the array.")
        ] = None,
        spare_devices: Annotated[
            list[int] | None, Field(description="MAAS ids of spare block devices.")
        ] = None,
        spare_partitions: Annotated[
            list[int] | None, Field(description="MAAS ids of spare partitions.")
        ] = None,
        hostname: Annotated[
            str | None,
            Field(description="Exact hostname of the machine; resolved to system_id server-side."),
        ] = None,
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> Raid:
        system_id = await resolve_system_id(client, system_id, hostname)
        _validate_ids(system_id)
        block_devices = block_devices or []
        partitions = partitions or []
        spare_devices = spare_devices or []
        spare_partitions = spare_partitions or []
        if level not in (0, 1, 5, 6, 10):
            raise ValueError(f"raid level must be 0, 1, 5, 6, or 10 (got {level})")
        if not (block_devices or partitions):
            raise ValueError("raid requires at least one block device or partition")
        if confirm is not True:
            raise ValueError(
                "create_raid is destructive; pass confirm=True to proceed. "
                f"Affected: system_id={system_id}, hostname={hostname}, level={level}"
            )
        body: dict[str, Any] = {"level": _RAID_LEVEL_TO_MAAS[level]}
        if name is not None:
            body["name"] = name
        if uuid is not None:
            body["uuid"] = uuid
        if block_devices:
            body["block_devices"] = block_devices
        if partitions:
            body["partitions"] = partitions
        if spare_devices:
            body["spare_devices"] = spare_devices
        if spare_partitions:
            body["spare_partitions"] = spare_partitions
        resp: Raid = await client.post(raids_path(system_id), json=body)
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for created raid "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return resp
