"""create_subnet: POST /subnets/."""

from __future__ import annotations

import ipaddress
from typing import Annotated, Any, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import _validate_id, subnets_path
from maasmcp.curated._schemas.network import Subnet
from maasmcp.maas.client import MaasClient


def _join_dns_servers(dns_servers: list[str]) -> str:
    """MAAS declares ``dns_servers`` a single comma-separated string; the
    client's list expansion into repeated form parts only survives if the
    server reads the field with getlist(). Send one part, comma-joined."""
    for server in dns_servers:
        ipaddress.ip_address(server)
    return ",".join(dns_servers)


class CreateSubnetTool:
    name = "create_subnet"
    description = (
        "Create a subnet in MAAS (POST /subnets/). "
        "Placement: pass vlan (MAAS internal VLAN id), or fabric_id (MAAS then uses "
        "that fabric's default VLAN), or vid together with fabric/spacing rules; "
        "cidr is required, gateway_ip/dns_servers are optional. "
        "Use this after create_fabric/create_vlan and before create_ip_range. "
        "Returns the newly-created subnet dict. "
        "State-mutating — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        cidr: Annotated[str, Field(description="Valid CIDR for the subnet (e.g. '10.0.0.0/24').")],
        fabric_id: Annotated[
            int | None,
            Field(
                description="MAAS id of the fabric to place the subnet in (the subnet lands on "
                "the fabric's untagged default VLAN unless vlan is also given)."
            ),
        ] = None,
        vlan: Annotated[
            int | None,
            Field(
                description="MAAS internal VLAN id (primary key) to associate with the "
                "subnet. This is NOT the IEEE 802.1Q VID — use vid for that."
            ),
        ] = None,
        vid: Annotated[
            int | None,
            Field(
                description="IEEE 802.1Q VLAN ID (1-4094) of the VLAN the subnet belongs to. "
                "Only used when vlan is not provided; combine with fabric_id if the VLAN ID "
                "exists on more than one fabric."
            ),
        ] = None,
        name: Annotated[
            str | None, Field(description="Optional display name for the subnet.")
        ] = None,
        description: Annotated[
            str | None, Field(description="Optional human-readable description.")
        ] = None,
        gateway_ip: Annotated[
            str | None, Field(description="Gateway IP address for the subnet.")
        ] = None,
        dns_servers: Annotated[
            list[str] | None, Field(description="List of DNS server IP addresses.")
        ] = None,
        rdns_mode: Annotated[
            int | None,
            Field(
                description="How reverse DNS is handled: 0 = Disabled, 1 = Enabled (zones "
                "generated per RFC1034), 2 = RFC2317 (covers /24-/32s)."
            ),
        ] = None,
        allow_dns: Annotated[
            int | None,
            Field(description="0 = False, 1 = True: allow MAAS DNS resolution of the subnet."),
        ] = None,
        allow_proxy: Annotated[
            int | None,
            Field(
                description="0 = False, 1 = True: allow MAAS to be used as a proxy for the subnet."
            ),
        ] = None,
        active_discovery: Annotated[
            int | None,
            Field(description="0 = False, 1 = True: actively scan the subnet to manage hosts."),
        ] = None,
        managed: Annotated[
            int | None,
            Field(
                description="0 = False, 1 = True: whether MAAS manages IP allocation for the "
                "subnet (default 1 / True)."
            ),
        ] = None,
        disabled_boot_architectures: Annotated[
            list[str] | None,
            Field(
                description="Boot architectures for which this subnet must not be used for "
                "booting (e.g. ['ipxe'])."
            ),
        ] = None,
        confirm: Annotated[
            bool, Field(description="Must be True to proceed. This operation is destructive.")
        ] = False,
    ) -> Subnet:
        try:
            ipaddress.ip_network(cidr, strict=True)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"invalid cidr {cidr!r}: {exc}") from exc
        if fabric_id is not None:
            _validate_id(fabric_id=fabric_id, _allow_zero=True)
        if vlan is not None:
            _validate_id(vlan=vlan)
        if vid is not None and not 1 <= vid <= 4094:
            raise ValueError(f"vlan vid must be in 1..4094 (got {vid})")
        if confirm is not True:
            raise ValueError(
                f"create_subnet is destructive; pass confirm=True to proceed. Affected: cidr={cidr}"
            )
        body: dict[str, Any] = {"cidr": cidr}
        if fabric_id is not None:
            body["fabric"] = fabric_id
        if vlan is not None:
            body["vlan"] = vlan
        if vid is not None:
            body["vid"] = vid
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if gateway_ip is not None:
            body["gateway_ip"] = gateway_ip
        if dns_servers is not None:
            body["dns_servers"] = _join_dns_servers(dns_servers)
        if rdns_mode is not None:
            body["rdns_mode"] = rdns_mode
        if allow_dns is not None:
            body["allow_dns"] = allow_dns
        if allow_proxy is not None:
            body["allow_proxy"] = allow_proxy
        if active_discovery is not None:
            body["active_discovery"] = active_discovery
        if managed is not None:
            body["managed"] = managed
        if disabled_boot_architectures is not None:
            body["disabled_boot_architectures"] = disabled_boot_architectures
        resp = await client.post(subnets_path(), json=body)
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for created subnet "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return cast(Subnet, resp)
