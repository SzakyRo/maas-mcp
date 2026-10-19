"""get_ip_range: GET /ipranges/{id}/."""

from __future__ import annotations

from typing import Annotated, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import _validate_id, ip_range_path
from maasmcp.curated._schemas.network import IpRange
from maasmcp.maas.client import MaasClient


class GetIpRangeTool:
    name = "get_ip_range"
    description = (
        "Fetch one MAAS IP range by its numeric id. "
        "Use this after list_ip_ranges to discover ids. "
        "Returns the MAAS IP-range dict (id, type, start_ip, end_ip, subnet, "
        "comment, etc.). "
        "Read-only; no confirmation needed."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        ip_range_id: Annotated[int, Field(description="MAAS id of the IP range.")],
    ) -> IpRange:
        _validate_id(ip_range_id=ip_range_id)
        resp = await client.get(ip_range_path(ip_range_id))
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for ip_range {ip_range_id} "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return cast(IpRange, resp)
