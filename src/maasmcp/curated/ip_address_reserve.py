"""ip_address_reserve: POST /api/2.0/ipaddresses/op-reserve."""

from __future__ import annotations

from typing import Annotated, Any, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._schemas.network import IpAddress
from maasmcp.maas.client import MaasClient


class IpAddressReserveTool:
    name = "ip_address_reserve"
    description = (
        "Reserve an IP address for use outside of MAAS. Use this to hold an "
        "address so MAAS will not hand it to any node; supply either a subnet "
        "CIDR (MAAS picks a free address) or a specific ip within a known "
        "subnet. Optionally link a hostname (default domain applied if "
        "unqualified) and/or a MAC address to the reservation. Fails with 400 "
        "if the subnet/ip does not resolve to a known MAAS subnet, and with "
        "503 if no addresses are available in the subnet. The reservation "
        "persists until released with ip_address_release. Returns the "
        "reserved IP address object. "
        "State-mutating — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        subnet: Annotated[
            str | None,
            Field(description="CIDR of the subnet to reserve in, e.g. 10.1.2.0/24."),
        ] = None,
        ip: Annotated[
            str | None,
            Field(description="Specific IP address to reserve; must be within a known subnet."),
        ] = None,
        hostname: Annotated[
            str | None,
            Field(description="Hostname for the reservation (default domain if unqualified)."),
        ] = None,
        mac: Annotated[
            str | None,
            Field(description="MAC address to link to this reservation."),
        ] = None,
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation mutates state.")
        ] = False,
    ) -> IpAddress:
        if subnet is None and ip is None:
            raise ValueError("ip_address_reserve requires subnet (CIDR) or a specific ip")
        if confirm is not True:
            raise ValueError(
                "ip_address_reserve mutates state; pass confirm=True to proceed. "
                f"Affected: subnet={subnet!r}, ip={ip!r}, hostname={hostname!r}, mac={mac!r}"
            )
        body: dict[str, Any] = {}
        if subnet is not None:
            body["subnet"] = subnet
        if ip is not None:
            body["ip"] = ip
        if hostname is not None:
            body["hostname"] = hostname
        if mac is not None:
            body["mac"] = mac
        resp = await client.post("/api/2.0/ipaddresses/op-reserve", json=body)
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for ip_address_reserve response "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return cast(IpAddress, resp)
