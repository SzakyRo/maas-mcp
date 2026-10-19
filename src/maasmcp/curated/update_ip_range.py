"""update_ip_range: PUT /ipranges/{id}/."""

from __future__ import annotations

import ipaddress
from typing import Annotated, Any, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import _validate_id, ip_range_path
from maasmcp.curated._schemas.network import IpRange
from maasmcp.maas.client import MaasClient


class UpdateIpRangeTool:
    name = "update_ip_range"
    description = (
        "Update an existing IP range (reserved or dynamic). "
        "Use this to adjust start/end addresses or edit the comment on a range "
        "obtained from list_ip_ranges. Both bounds are validated locally; when "
        "you move only one of them, the range must still make sense against the "
        "other (unchanged) bound on MAAS's side. "
        "Returns the updated IP range dict. "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        ip_range_id: Annotated[int, Field(description="MAAS id of the IP range to update.")],
        start_ip: Annotated[
            str | None, Field(description="New start IP address (inclusive).")
        ] = None,
        end_ip: Annotated[str | None, Field(description="New end IP address (inclusive).")] = None,
        comment: Annotated[str | None, Field(description="New comment for the range.")] = None,
        confirm: Annotated[
            bool,
            Field(description="Must be True to proceed. This operation is destructive."),
        ] = False,
    ) -> IpRange:
        _validate_id(ip_range_id=ip_range_id)
        parsed_start, parsed_end = None, None
        try:
            if start_ip is not None:
                parsed_start = ipaddress.ip_address(start_ip)
            if end_ip is not None:
                parsed_end = ipaddress.ip_address(end_ip)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"invalid start_ip/end_ip ({start_ip!r}, {end_ip!r}): {exc}") from exc
        if (
            parsed_start is not None
            and parsed_end is not None
            and int(parsed_start) > int(parsed_end)
        ):
            raise ValueError(f"start_ip {start_ip} must be <= end_ip {end_ip}")
        if confirm is not True:
            raise ValueError(
                "update_ip_range is destructive; pass confirm=True to proceed. "
                f"Affected: ip_range_id={ip_range_id}"
            )
        body: dict[str, Any] = {}
        if start_ip is not None:
            body["start_ip"] = start_ip
        if end_ip is not None:
            body["end_ip"] = end_ip
        if comment is not None:
            body["comment"] = comment
        resp = await client.put(ip_range_path(ip_range_id), json=body)
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for updated ip_range "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return cast(IpRange, resp)
