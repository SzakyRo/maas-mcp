"""create_volume_group: POST /nodes/{system_id}/volume-groups/."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.storage import VolumeGroup
from maasmcp.curated._storage_paths import _validate_ids, volume_groups_path
from maasmcp.maas.client import MaasClient


class CreateVolumeGroupTool:
    name = "create_volume_group"
    description = (
        "Create a volume group on a MAAS machine. "
        "Use this to aggregate one or more block devices or partitions into a "
        "single VG; logical volumes can then be created inside it with "
        "create_logical_volume. "
        "Returns the newly-created volume group dict. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        name: Annotated[str, Field(description="Name for the new volume group.")],
        *,
        system_id: Annotated[
            str | None,
            Field(
                description="MAAS system_id of the machine. "
                "Provide this or hostname, exactly one."
            ),
        ] = None,
        uuid: Annotated[
            str | None, Field(description="Optional UUID to assign to the volume group.")
        ] = None,
        block_devices: Annotated[
            list[int] | None,
            Field(description="Optional list of block device ids to include in the VG."),
        ] = None,
        partitions: Annotated[
            list[int] | None,
            Field(description="Optional list of partition ids to include in the VG."),
        ] = None,
        hostname: Annotated[
            str | None,
            Field(description="Exact hostname of the machine; resolved to system_id server-side."),
        ] = None,
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> VolumeGroup:
        system_id = await resolve_system_id(client, system_id, hostname)
        _validate_ids(system_id)
        block_devices = block_devices or []
        partitions = partitions or []
        if not name:
            raise ValueError("name must be a non-empty string")
        if not (block_devices or partitions):
            raise ValueError("volume group requires at least one block device or partition")
        if confirm is not True:
            raise ValueError(
                "create_volume_group is destructive; pass confirm=True to proceed. "
                f"Affected: system_id={system_id}, hostname={hostname}, name={name}"
            )
        body: dict[str, Any] = {"name": name}
        if uuid is not None:
            body["uuid"] = uuid
        if block_devices:
            body["block_devices"] = block_devices
        if partitions:
            body["partitions"] = partitions
        resp: VolumeGroup = await client.post(volume_groups_path(system_id), json=body)
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for created volume group "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return resp
