"""ip_address_release: POST /api/2.0/ipaddresses/op-release."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.maas.client import MaasClient


class IpAddressReleaseTool:
    name = "ip_address_release"
    description = (
        "Release an IP address that was previously reserved. Use this to free "
        "a reservation left behind by an earlier deployment — note that "
        "unlinking a static subnet link from an interface does NOT free the "
        "underlying reserved address. force allows an admin to release an "
        "address owned by another user or of a non-user-reserved type; "
        "discovered (only valid with force) releases observed addresses. "
        "Returns nothing on success (MAAS replies 204). "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        ip: Annotated[str, Field(description="The IP address to release.")],
        force: Annotated[
            bool,
            Field(
                description="Admin: release even if the address is not user-reserved "
                "or belongs to another user. Use with caution."
            ),
        ] = False,
        discovered: Annotated[
            bool,
            Field(
                description="Admin: also release discovered addresses. Only valid "
                "together with force=True."
            ),
        ] = False,
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> None:
        if not ip:
            raise ValueError("ip must be a non-empty string")
        if discovered and not force:
            raise ValueError("discovered=True is only valid together with force=True (MAAS rule)")
        if confirm is not True:
            raise ValueError(
                "ip_address_release is destructive; pass confirm=True to proceed. "
                f"Affected: ip={ip!r}, force={force}, discovered={discovered}"
            )
        body: dict[str, Any] = {"ip": ip}
        if force:
            body["force"] = True
        if discovered:
            body["discovered"] = True
        await client.post("/api/2.0/ipaddresses/op-release", json=body)
