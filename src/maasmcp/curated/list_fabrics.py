"""list_fabrics: GET /fabrics/."""

from __future__ import annotations

from typing import Annotated

from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import fabrics_path
from maasmcp.curated._schemas.network import Fabric
from maasmcp.maas.client import MaasClient


class ListFabricsTool:
    name = "list_fabrics"
    description = (
        "List all fabrics in MAAS. Use this to enumerate fabrics before "
        "calling list_vlans(fabric_id=...) or get_fabric(id=...). Returns a "
        "list of fabric dicts. Read-only; no confirmation needed."
    )

    async def run(self, client: Annotated[MaasClient, SkipJsonSchema()]) -> list[Fabric]:
        resp = await client.get(fabrics_path())
        if isinstance(resp, dict) and "fabrics" in resp:
            return list(resp["fabrics"])
        if isinstance(resp, list):
            return resp
        return []
