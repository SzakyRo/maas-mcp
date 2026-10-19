"""list_ip_ranges: GET /ipranges/."""

from __future__ import annotations

from typing import Annotated

from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import ip_ranges_path
from maasmcp.curated._schemas.network import IpRange
from maasmcp.maas.client import MaasClient


class ListIpRangesTool:
    name = "list_ip_ranges"
    description = (
        "List all IP ranges in MAAS. Use this to enumerate ranges before "
        "creating, updating, or deleting one. Returns a list of IP range "
        "dicts. Read-only; no confirmation needed."
    )

    async def run(self, client: Annotated[MaasClient, SkipJsonSchema()]) -> list[IpRange]:
        resp = await client.get(ip_ranges_path())
        if isinstance(resp, dict) and "ipranges" in resp:
            return list(resp["ipranges"])
        if isinstance(resp, list):
            return resp
        return []
