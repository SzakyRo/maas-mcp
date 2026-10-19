"""delete_ip_range: DELETE /ipranges/{id}/."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import _validate_id, ip_range_path
from maasmcp.maas.client import MaasClient


class DeleteIpRangeTool:
    name = "delete_ip_range"
    description = (
        "Delete an IP range from a subnet. "
        "Use this to remove a reserved or dynamic range after verifying it is no "
        "longer in use (see list_ip_ranges and get_ip_range). "
        "Returns nothing on success. "
        "DESTRUCTIVE (cluster-wide) — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        ip_range_id: Annotated[int, Field(description="MAAS id of the IP range to delete.")],
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> None:
        _validate_id(ip_range_id=ip_range_id)
        if confirm is not True:
            raise ValueError(
                "delete_ip_range is destructive; pass confirm=True to proceed. "
                f"Affected: ip_range_id={ip_range_id}"
            )
        await client.delete(ip_range_path(ip_range_id))
