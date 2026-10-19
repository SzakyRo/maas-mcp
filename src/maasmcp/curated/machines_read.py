"""machines_read: GET /machines/."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from maasmcp.maas.client import MaasClient


class MachinesReadTool:
    name = "machines_read"
    description = (
        "Read machines in MAAS. "
        "Use this when you need the raw MAAS response or the curated "
        "list_machines verb does not expose the filters you need. "
        "Returns a list of machine objects or the raw collection. "
        "Read-only; no confirmation needed."
    )

    async def run(
        self,
        client: Annotated[MaasClient, SkipJsonSchema()],
        hostname: Annotated[
            str | None,
            Field(
                description="Only nodes relating to the node with the matching hostname will be returned. This can be specified multiple times to see multiple nodes."
            ),
        ] = None,
        cpu_count: Annotated[
            int | None,
            Field(
                description="Only nodes with the specified minimum number of CPUs will be included."
            ),
        ] = None,
        mem: Annotated[
            str | None,
            Field(
                description="Only nodes with the specified minimum amount of RAM (in MiB) will be included."
            ),
        ] = None,
        mac_address: Annotated[
            str | None,
            Field(
                description="Only nodes relating to the node owning the specified MAC address will be returned. This can be specified multiple times to see multiple nodes."
            ),
        ] = None,
        id: Annotated[
            str | None,
            Field(
                description="Only nodes relating to the nodes with matching system ids will be returned."
            ),
        ] = None,
        domain: Annotated[
            str | None,
            Field(description="Only nodes relating to the nodes in the domain will be returned."),
        ] = None,
        zone: Annotated[
            str | None,
            Field(description="Only nodes relating to the nodes in the zone will be returned."),
        ] = None,
        pool: Annotated[
            str | None,
            Field(description="Only nodes belonging to the pool will be returned."),
        ] = None,
        agent_name: Annotated[
            str | None,
            Field(
                description="Only nodes relating to the nodes with matching agent names will be returned."
            ),
        ] = None,
        status: Annotated[
            str | None,
            Field(
                description="Only nodes with the specified status will be returned "
                "(e.g. 'ready', 'deployed', 'etc' — the lowercase status name)."
            ),
        ] = None,
        fabrics: Annotated[
            str | None,
            Field(description="Only nodes with interfaces in specified fabrics will be returned."),
        ] = None,
        not_fabrics: Annotated[
            str | None,
            Field(
                description="Only nodes with interfaces not in specified fabrics will be returned."
            ),
        ] = None,
        vlans: Annotated[
            str | None,
            Field(description="Only nodes with interfaces in specified VLANs will be returned."),
        ] = None,
        not_vlans: Annotated[
            str | None,
            Field(
                description="Only nodes with interfaces not in specified VLANs will be returned."
            ),
        ] = None,
        subnets: Annotated[
            str | None,
            Field(description="Only nodes with interfaces in specified subnets will be returned."),
        ] = None,
        not_subnets: Annotated[
            str | None,
            Field(
                description="Only nodes with interfaces not in specified subnets will be returned."
            ),
        ] = None,
        link_speed: Annotated[
            str | None,
            Field(
                description="Only nodes with interfaces with link speeds greater than or equal to link_speed will be returned."
            ),
        ] = None,
        pod: Annotated[
            str | None,
            Field(description="Only nodes that belong to a specified pod will be returned."),
        ] = None,
        not_pod: Annotated[
            str | None,
            Field(description="Only nodes that don't belong to a specified pod will be returned."),
        ] = None,
        pod_type: Annotated[
            str | None,
            Field(
                description="Only nodes that belong to a pod of the specified type will be returned."
            ),
        ] = None,
        not_pod_type: Annotated[
            str | None,
            Field(
                description="Only nodes that don't belong a pod of the specified type will be returned."
            ),
        ] = None,
        devices: Annotated[
            str | None,
            Field(
                description="Only return nodes which have one or more devices containing the following constraints in the format key=value[,key2=value2[,...]]"
            ),
        ] = None,
        paginate: Annotated[
            bool,
            Field(
                description="Set to True to auto-paginate through limit/offset up to max_paginated_items. False (default) returns a single MAAS page."
            ),
        ] = False,
    ) -> dict[str, Any] | list[dict[str, Any]] | None:
        # Strip the internal ``paginate`` flag before sending — MAAS
        # would treat it as a query param and 302-redirect us.
        params = {
            k: v
            for k, v in {
                "hostname": hostname,
                "cpu_count": cpu_count,
                "mem": mem,
                "mac_address": mac_address,
                "id": id,
                "domain": domain,
                "zone": zone,
                "pool": pool,
                "agent_name": agent_name,
                "status": status,
                "fabrics": fabrics,
                "not_fabrics": not_fabrics,
                "vlans": vlans,
                "not_vlans": not_vlans,
                "subnets": subnets,
                "not_subnets": not_subnets,
                "link_speed": link_speed,
                "pod": pod,
                "not_pod": not_pod,
                "pod_type": pod_type,
                "not_pod_type": not_pod_type,
                "devices": devices,
            }.items()
            if v is not None
        }
        return await client.paginated_get(  # type: ignore[no-any-return]
            "/api/2.0/machines/", params=params, paginate=paginate
        )
