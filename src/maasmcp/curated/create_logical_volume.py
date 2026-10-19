"""create_logical_volume: POST /nodes/{system_id}/volume-group/{vg_id}/op-create_logical_volume."""

from __future__ import annotations

from typing import Annotated, Any, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._resolve import resolve_system_id
from maasmcp.curated._schemas.storage import LogicalVolume
from maasmcp.curated._storage_paths import _validate_ids, lv_create_path
from maasmcp.maas.client import MaasClient


class CreateLogicalVolumeTool:
    name = "create_logical_volume"
    description = (
        "Create a logical volume inside a MAAS volume group. "
        "Use this after creating a volume group (create_volume_group) and before "
        "using the volume for partitioning or deployment. "
        "Returns the newly-created logical-volume dict, or the parent volume group "
        "dict if MAAS returns it; verify membership via get_volume_group. "
        "Accepts system_id or hostname (provide exactly one). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        vg_id: Annotated[int, Field(description="MAAS id of the volume group.")],
        name: Annotated[str, Field(description="Name for the new logical volume.")],
        *,
        system_id: Annotated[
            str | None,
            Field(
                description="MAAS system_id of the machine. "
                "Provide this or hostname, exactly one."
            ),
        ] = None,
        uuid: Annotated[
            str | None, Field(description="Optional UUID to assign to the logical volume.")
        ] = None,
        size: Annotated[
            str | None,
            Field(
                description="Size of the logical volume in bytes (e.g. '4194304'; minimum "
                "4,194,304) or a number with one unit suffix such as '100G'. "
                "Omit to consume all free space in the volume group."
            ),
        ] = None,
        hostname: Annotated[
            str | None,
            Field(description="Exact hostname of the machine; resolved to system_id server-side."),
        ] = None,
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> LogicalVolume:
        system_id = await resolve_system_id(client, system_id, hostname)
        _validate_ids(system_id, vg_id=vg_id)
        if not name:
            raise ValueError("name must be a non-empty string")
        if confirm is not True:
            raise ValueError(
                "create_logical_volume is destructive; pass confirm=True to proceed. "
                f"Affected: system_id={system_id}, hostname={hostname}, vg_id={vg_id}, name={name}"
            )
        body: dict[str, Any] = {"name": name}
        if uuid is not None:
            body["uuid"] = uuid
        if size is not None:
            body["size"] = size
        resp = await client.post(lv_create_path(system_id, vg_id), json=body)
        if isinstance(resp, dict):
            return cast(LogicalVolume, resp)
        return cast(LogicalVolume, {})
