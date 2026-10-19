"""delete_subnet: DELETE /subnets/{id}/."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import _validate_id, subnet_path
from maasmcp.maas.client import MaasClient


class DeleteSubnetTool:
    name = "delete_subnet"
    description = (
        "Delete a subnet. "
        "Use this after clearing its IP ranges and linked interfaces (see "
        "unlink_subnet, delete_ip_range, list_subnets). Fails if IP addresses on "
        "the subnet are in use by nodes unless force=True is passed — force deletes "
        "the subnet even with in-use addresses. "
        "Returns nothing on success. "
        "DESTRUCTIVE (cluster-wide, affects every interface on the subnet) — "
        "must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        subnet_id: Annotated[int, Field(description="MAAS id of the subnet to delete.")],
        force: Annotated[
            bool,
            Field(
                description="If True, delete the subnet even if it has IP addresses in use "
                "by nodes. Defaults to False."
            ),
        ] = False,
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> None:
        _validate_id(subnet_id=subnet_id)
        if confirm is not True:
            raise ValueError(
                "delete_subnet is destructive; pass confirm=True to proceed. "
                f"Affected: subnet_id={subnet_id}"
            )
        path = subnet_path(subnet_id)
        if force:
            # DELETE takes no body; force travels as a query parameter.
            path = f"{path}?force=1"
        await client.delete(path)
