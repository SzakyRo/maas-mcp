"""create_ip_range: POST /ipranges/."""

from __future__ import annotations

import ipaddress
from typing import Annotated, Any, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import _validate_id, ip_ranges_path
from maasmcp.curated._schemas.network import IpRange
from maasmcp.maas.client import MaasClient


class CreateIpRangeTool:
    name = "create_ip_range"
    description = (
        "Create an IP range on a subnet. "
        "Use this to reserve dynamic or reserved address blocks after the "
        "subnet exists (create_subnet first if needed). "
        "Returns the newly-created IP-range dict. "
        "DESTRUCTIVE (cluster-wide) — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        subnet_id: Annotated[
            int, Field(description="MAAS id of the subnet to attach the range to.")
        ],
        start_ip: Annotated[str, Field(description="First IP address in the range (inclusive).")],
        end_ip: Annotated[str, Field(description="Last IP address in the range (inclusive).")],
        range_type: Annotated[
            str, Field(description="Range type: 'dynamic' or 'reserved'.")
        ] = "dynamic",
        comment: Annotated[
            str | None, Field(description="Optional comment or description for the range.")
        ] = None,
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> IpRange:
        _validate_id(subnet_id=subnet_id)
        try:
            start = ipaddress.ip_address(start_ip)
            end = ipaddress.ip_address(end_ip)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"invalid start_ip/end_ip ({start_ip!r}, {end_ip!r}): {exc}") from exc
        if int(start) > int(end):
            raise ValueError(f"start_ip {start_ip} must be <= end_ip {end_ip}")
        if confirm is not True:
            raise ValueError(
                "create_ip_range is destructive; pass confirm=True to proceed. "
                f"Affected: subnet_id={subnet_id}, range={start_ip}..{end_ip}"
            )
        body: dict[str, Any] = {
            "subnet": subnet_id,
            "start_ip": start_ip,
            "end_ip": end_ip,
            "type": range_type,
        }
        if comment is not None:
            body["comment"] = comment
        resp = await client.post(ip_ranges_path(), json=body)
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for created ip_range "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return cast(IpRange, resp)
