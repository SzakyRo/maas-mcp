"""list_subnets: GET /subnets/."""

from __future__ import annotations

from typing import Annotated

from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import subnets_path
from maasmcp.curated._schemas.network import Subnet
from maasmcp.maas.client import MaasClient


class ListSubnetsTool:
    name = "list_subnets"
    description = (
        "List all subnets in MAAS. Use this before create_subnet, "
        "update_subnet, delete_subnet, or link_subnet. Returns a list of "
        "subnet dicts. Read-only; no confirmation needed."
    )

    async def run(self, client: Annotated[MaasClient, SkipJsonSchema()]) -> list[Subnet]:
        resp = await client.get(subnets_path())
        if isinstance(resp, dict) and "subnets" in resp:
            return list(resp["subnets"])
        if isinstance(resp, list):
            return resp
        return []
