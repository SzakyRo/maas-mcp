"""get_volume_group: GET /nodes/{system_id}/volume-group/{id}/."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.storage import VolumeGroup
from maasmcp.curated._storage_paths import _validate_ids, volume_group_path
from maasmcp.maas.client import MaasClient


class GetVolumeGroupTool:
    name = "get_volume_group"
    description = (
        "Fetch one LVM volume group on a machine by its numeric id. "
        "Use this after list_volume_groups to discover the vg_id. "
        "Returns the MAAS volume-group dict (id, name, size, logical_volumes, "
        "block_devices, partitions, etc.). "
        "Accepts system_id or hostname (provide exactly one). "
        "Read-only; no confirmation needed."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        vg_id: Annotated[int, Field(description="MAAS id of the volume group.")],
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
    ) -> VolumeGroup:
        system_id = await resolve_system_id(client, system_id, hostname)
        _validate_ids(system_id, vg_id=vg_id)
        resp: VolumeGroup = await client.get(volume_group_path(system_id, vg_id))
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for volume group {vg_id} "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return resp
