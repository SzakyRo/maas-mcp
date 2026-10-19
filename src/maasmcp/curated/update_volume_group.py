"""update_volume_group: PUT /nodes/{system_id}/volume-group/{id}/."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.storage import VolumeGroup
from maasmcp.curated._storage_paths import _validate_ids, volume_group_path
from maasmcp.maas.client import MaasClient


class UpdateVolumeGroupTool:
    name = "update_volume_group"
    description = (
        "Update a volume group on a machine (rename, set UUID, or add/remove "
        "block devices and partitions). "
        "Use this to adjust VG membership or metadata after creation; first call "
        "list_volume_groups or get_volume_group to find the target. "
        "To change physical volumes, pass the ids of block devices or partitions "
        "to add or remove. "
        "Returns the updated volume group dict. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        vg_id: Annotated[int, Field(description="MAAS id of the volume group to update.")],
        *,
        system_id: Annotated[
            str | None,
            Field(
                description="MAAS system_id of the machine. "
                "Provide this or hostname, exactly one."
            ),
        ] = None,
        name: Annotated[
            str | None,
            Field(
                description="New name for the volume group. Leave unset to keep the current name."
            ),
        ] = None,
        uuid: Annotated[
            str | None,
            Field(
                description="UUID to assign to the volume group. Leave unset to keep the current UUID."
            ),
        ] = None,
        add_block_devices: Annotated[
            list[int] | None,
            Field(description="List of block device ids to add as physical volumes."),
        ] = None,
        remove_block_devices: Annotated[
            list[int] | None,
            Field(description="List of block device ids to remove from the group."),
        ] = None,
        add_partitions: Annotated[
            list[int] | None,
            Field(description="List of partition ids to add as physical volumes."),
        ] = None,
        remove_partitions: Annotated[
            list[int] | None,
            Field(description="List of partition ids to remove from the group."),
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
        _validate_ids(system_id, vg_id=vg_id)
        add_block_devices = add_block_devices or []
        remove_block_devices = remove_block_devices or []
        add_partitions = add_partitions or []
        remove_partitions = remove_partitions or []
        if confirm is not True:
            raise ValueError(
                "update_volume_group is destructive; pass confirm=True to proceed. "
                f"Affected: system_id={system_id}, hostname={hostname}, vg_id={vg_id}"
            )
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if uuid is not None:
            body["uuid"] = uuid
        if add_block_devices:
            body["add_block_devices"] = add_block_devices
        if remove_block_devices:
            body["remove_block_devices"] = remove_block_devices
        if add_partitions:
            body["add_partitions"] = add_partitions
        if remove_partitions:
            body["remove_partitions"] = remove_partitions
        if not body:
            raise ValueError(
                "update_volume_group: nothing to update — pass at least one field to change."
            )
        resp: VolumeGroup = await client.put(volume_group_path(system_id, vg_id), json=body)
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for updated volume group {vg_id} "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return resp
