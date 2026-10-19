"""get_subnet: GET /subnets/{id}/."""

from __future__ import annotations

from typing import Annotated, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import _validate_id, subnet_path
from maasmcp.curated._schemas.network import Subnet
from maasmcp.maas.client import MaasClient


class GetSubnetTool:
    name = "get_subnet"
    description = (
        "Fetch one MAAS subnet by its numeric id. "
        "Use this after list_subnets to discover ids. "
        "Returns the MAAS subnet dict (id, cidr, gateway_ip, dns_servers, vlan, "
        "space, etc.). "
        "Read-only; no confirmation needed."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        subnet_id: Annotated[int, Field(description="MAAS id of the subnet.")],
    ) -> Subnet:
        _validate_id(subnet_id=subnet_id)
        resp = await client.get(subnet_path(subnet_id))
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for subnet {subnet_id} "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return cast(Subnet, resp)
