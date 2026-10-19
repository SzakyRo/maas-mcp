"""ip_addresses_read: GET /api/2.0/ipaddresses/."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.maas.client import MaasClient

PATH = "/api/2.0/ipaddresses/"


class IpAddressesReadTool:
    name = "ip_addresses_read"
    description = (
        "List IP addresses known to MAAS. Use this to check whether an "
        "address is reserved or in use — e.g. when link_subnet reports "
        "'IP address is already in use' after an unlink: a stale reservation "
        "outlives the interface link until released. By default MAAS lists only "
        "addresses of type 'User reserved' owned by the requesting user; admins "
        "can pass all=True to see everything, or owner=<username> to filter. "
        "Returns a list of IP address objects. "
        "Read-only; no confirmation needed."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        ip: Annotated[
            str | None,
            Field(description="If specified, only display information for this IP address."),
        ] = None,
        all: Annotated[
            bool | None,
            Field(
                description="(Admin only) If True, show all reserved IP addresses; "
                "by default only user-reserved addresses owned by the caller are shown."
            ),
        ] = None,
        owner: Annotated[
            str | None,
            Field(description="(Admin only) Filter to IP addresses owned by this username."),
        ] = None,
        paginate: Annotated[
            bool,
            Field(
                description="Set to True to auto-paginate through limit/offset up to "
                "max_paginated_items. False (default) returns a single MAAS page."
            ),
        ] = False,
    ) -> dict[str, Any] | list[dict[str, Any]] | None:
        # MAAS response shape varies (single-page dict vs bare list vs None);
        # left loosely typed intentionally. See _schemas.network.IpAddress for
        # the documented/common fields of individual IP address records.
        # Strip internal/pagination flag — it must not go on the wire.
        params = {k: v for k, v in {"ip": ip, "all": all, "owner": owner}.items() if v is not None}
        return await client.paginated_get(PATH, params=params, paginate=paginate)  # type: ignore[no-any-return]
