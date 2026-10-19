"""update_raid: PUT /nodes/{system_id}/raid/{id}/."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.storage import Raid
from maasmcp.curated._storage_paths import _validate_ids, raid_path
from maasmcp.maas.client import MaasClient


class UpdateRaidTool:
    name = "update_raid"
    description = (
        "Update a RAID array (rename, add or remove active members, spares, or partitions). "
        "Use this after create_raid to adjust array membership or rename the array; "
        "list_raids provides the raid_id and current members. "
        "Returns the updated RAID dict. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        raid_id: Annotated[int, Field(description="MAAS id of the RAID array to update.")],
        *,
        system_id: Annotated[
            str | None,
            Field(
                description="MAAS system_id of the machine. "
                "Provide this or hostname, exactly one."
            ),
        ] = None,
        name: Annotated[str | None, Field(description="New name for the RAID array.")] = None,
        uuid: Annotated[str | None, Field(description="New UUID for the RAID array.")] = None,
        add_block_devices: Annotated[
            list[int] | None,
            Field(description="Block device ids to add as active members."),
        ] = None,
        remove_block_devices: Annotated[
            list[int] | None,
            Field(description="Block device ids to remove from active members."),
        ] = None,
        add_spare_devices: Annotated[
            list[int] | None,
            Field(description="Block device ids to add as spare members."),
        ] = None,
        remove_spare_devices: Annotated[
            list[int] | None,
            Field(description="Block device ids to remove from spare members."),
        ] = None,
        add_partitions: Annotated[
            list[int] | None,
            Field(description="Partition ids to add as active members."),
        ] = None,
        remove_partitions: Annotated[
            list[int] | None,
            Field(description="Partition ids to remove from active members."),
        ] = None,
        add_spare_partitions: Annotated[
            list[int] | None,
            Field(description="Partition ids to add as spare members."),
        ] = None,
        remove_spare_partitions: Annotated[
            list[int] | None,
            Field(description="Partition ids to remove from spare members."),
        ] = None,
        hostname: Annotated[
            str | None,
            Field(description="Exact hostname of the machine; resolved to system_id server-side."),
        ] = None,
        confirm: Annotated[
            bool,
            Field(description="Must be True to proceed. This operation is destructive."),
        ] = False,
    ) -> Raid:
        system_id = await resolve_system_id(client, system_id, hostname)
        _validate_ids(system_id, raid_id=raid_id)
        add_block_devices = add_block_devices or []
        remove_block_devices = remove_block_devices or []
        add_spare_devices = add_spare_devices or []
        remove_spare_devices = remove_spare_devices or []
        add_partitions = add_partitions or []
        remove_partitions = remove_partitions or []
        add_spare_partitions = add_spare_partitions or []
        remove_spare_partitions = remove_spare_partitions or []
        if confirm is not True:
            raise ValueError(
                "update_raid is destructive; pass confirm=True to proceed. "
                f"Affected: system_id={system_id}, hostname={hostname}, raid_id={raid_id}"
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
        if add_spare_devices:
            body["add_spare_devices"] = add_spare_devices
        if remove_spare_devices:
            body["remove_spare_devices"] = remove_spare_devices
        if add_partitions:
            body["add_partitions"] = add_partitions
        if remove_partitions:
            body["remove_partitions"] = remove_partitions
        if add_spare_partitions:
            body["add_spare_partitions"] = add_spare_partitions
        if remove_spare_partitions:
            body["remove_spare_partitions"] = remove_spare_partitions
        if not body:
            raise ValueError(
                "update_raid: nothing to update — pass at least one field to change."
            )
        resp: Raid = await client.put(raid_path(system_id, raid_id), json=body)
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for updated raid {raid_id} "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return resp
