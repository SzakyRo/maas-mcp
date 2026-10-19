"""update_subnet: PUT /subnets/{id}/."""

from __future__ import annotations

import ipaddress
from typing import Annotated, Any, cast

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.curated._network_paths import _validate_id, subnet_path
from maasmcp.curated._schemas.network import Subnet
from maasmcp.curated.create_subnet import _join_dns_servers
from maasmcp.maas.client import MaasClient


class UpdateSubnetTool:
    name = "update_subnet"
    description = (
        "Update a subnet's metadata in place (name, description, gateway, DNS servers, "
        "VLAN placement). cidr, vid, rdns_mode, allow_dns/allow_proxy, active_discovery "
        "and managed are also updatable per the MAAS API. "
        "Returns the updated subnet dict. "
        "DESTRUCTIVE — must pass confirm=True; rejected otherwise."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        subnet_id: Annotated[int, Field(description="MAAS id of the subnet to update.")],
        name: Annotated[str | None, Field(description="New subnet name.")] = None,
        description: Annotated[str | None, Field(description="New subnet description.")] = None,
        cidr: Annotated[
            str | None,
            Field(description="New network CIDR for the subnet (updatable per the MAAS API)."),
        ] = None,
        gateway_ip: Annotated[
            str | None, Field(description="Gateway IP address for the subnet.")
        ] = None,
        dns_servers: Annotated[
            list[str] | None,
            Field(description="List of DNS server IP addresses for the subnet."),
        ] = None,
        vlan: Annotated[
            int | None,
            Field(description="MAAS internal VLAN id to associate with the subnet."),
        ] = None,
        vid: Annotated[
            int | None,
            Field(
                description="IEEE 802.1Q VID (1-4094) of the VLAN the subnet belongs to; "
                "only used when vlan is not provided."
            ),
        ] = None,
        fabric: Annotated[
            int | None,
            Field(description="MAAS id of the fabric this subnet is located in."),
        ] = None,
        rdns_mode: Annotated[
            int | None,
            Field(
                description="How reverse DNS is handled: 0 = Disabled, 1 = Enabled, 2 = RFC2317."
            ),
        ] = None,
        allow_dns: Annotated[
            int | None,
            Field(description="0 = False, 1 = True: allow MAAS DNS resolution of the subnet."),
        ] = None,
        allow_proxy: Annotated[
            int | None,
            Field(description="0 = False, 1 = True: allow MAAS as proxy for the subnet."),
        ] = None,
        active_discovery: Annotated[
            int | None,
            Field(description="0 = False, 1 = True: actively scan the subnet to manage hosts."),
        ] = None,
        managed: Annotated[
            int | None,
            Field(description="0 = False, 1 = True: whether MAAS manages IP allocation."),
        ] = None,
        disabled_boot_architectures: Annotated[
            list[str] | None,
            Field(
                description="Boot architectures for which this subnet must not be used for booting."
            ),
        ] = None,
        confirm: Annotated[
            bool,
            Field(description="Must be True to proceed. This operation is destructive."),
        ] = False,
    ) -> Subnet:
        _validate_id(subnet_id=subnet_id)
        if vlan is not None:
            _validate_id(vlan=vlan)
        if vid is not None and not 1 <= vid <= 4094:
            raise ValueError(f"vlan vid must be in 1..4094 (got {vid})")
        if fabric is not None:
            _validate_id(fabric=fabric, _allow_zero=True)
        if cidr is not None:
            try:
                ipaddress.ip_network(cidr, strict=True)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"invalid cidr {cidr!r}: {exc}") from exc
        if confirm is not True:
            raise ValueError(
                "update_subnet is destructive; pass confirm=True to proceed. "
                f"Affected: subnet_id={subnet_id}"
            )
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if cidr is not None:
            body["cidr"] = cidr
        if gateway_ip is not None:
            body["gateway_ip"] = gateway_ip
        if dns_servers is not None:
            body["dns_servers"] = _join_dns_servers(dns_servers)
        if vlan is not None:
            body["vlan"] = vlan
        if vid is not None:
            body["vid"] = vid
        if fabric is not None:
            body["fabric"] = fabric
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
        if not body:
            raise ValueError(
                "update_subnet: nothing to update — pass at least one field to change."
            )
        resp = await client.put(subnet_path(subnet_id), json=body)
        if not isinstance(resp, dict):
            raise ValueError(
                f"MAAS returned non-dict for updated subnet "
                f"(got {type(resp).__name__}); schema drift?"
            )
        return cast(Subnet, resp)
