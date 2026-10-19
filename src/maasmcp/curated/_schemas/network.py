"""Network-domain TypedDict return schemas for curated tools.

Mirrors ``base.py`` style: required fields are canonical ids only,
everything else is ``NotRequired`` so version drift does not invalidate
the MCP ``tools/list`` output schema. Runtime code still does best-effort
extraction; these schemas are documentation for the LLM agent.

Importers go directly to this module (the package ``__init__`` is the
shared ``base`` re-exporter and is intentionally not modified here).
"""

from __future__ import annotations

from typing import Any, NotRequired

from typing_extensions import TypedDict

from maasmcp.curated._schemas.base import VlanRef


class Fabric(TypedDict):
    """MAAS fabric record."""

    id: int
    name: NotRequired[str | None]
    description: NotRequired[str | None]
    class_type: NotRequired[str | None]
    vlans: NotRequired[list[dict[str, Any]]]


class Space(TypedDict):
    """MAAS space record."""

    id: int
    name: NotRequired[str | None]
    description: NotRequired[str | None]
    subnets: NotRequired[list[int]]
    vlans: NotRequired[list[int]]


class Vlan(TypedDict):
    """MAAS VLAN record."""

    id: int
    vid: NotRequired[int]
    name: NotRequired[str | None]
    description: NotRequired[str | None]
    fabric: NotRequired[int]
    mtu: NotRequired[int]
    dhcp_on: NotRequired[bool]
    primary_rack: NotRequired[str | None]
    secondary_rack: NotRequired[str | None]
    relay_vlan: NotRequired[int | None]
    space: NotRequired[str | int | None]


class Subnet(TypedDict):
    """MAAS subnet record."""

    id: int
    name: NotRequired[str | None]
    description: NotRequired[str | None]
    cidr: NotRequired[str]
    gateway_ip: NotRequired[str | None]
    dns_servers: NotRequired[str | list[str]]
    vlan: NotRequired[VlanRef | None]
    space: NotRequired[str | int | None]
    rdns_mode: NotRequired[int]
    allow_dns: NotRequired[int]
    allow_proxy: NotRequired[int]
    active_discovery: NotRequired[int]
    managed: NotRequired[int]
    disabled_boot_architectures: NotRequired[list[str]]


class IpRange(TypedDict):
    """MAAS IP range record."""

    id: int
    type: NotRequired[str]
    start_ip: NotRequired[str]
    end_ip: NotRequired[str]
    subnet: NotRequired[int | dict[str, Any]]
    comment: NotRequired[str | None]


class Interface(TypedDict):
    """MAAS interface record."""

    id: int
    name: NotRequired[str | None]
    type: NotRequired[str]
    mac_address: NotRequired[str | None]
    vlan_id: NotRequired[int | None]
    vlan: NotRequired[VlanRef | None]
    parents: NotRequired[list[int]]
    children: NotRequired[list[int]]
    ip_addresses: NotRequired[list[str]]
    links: NotRequired[list[dict[str, Any]]]
    tags: NotRequired[list[str]]
    mtu: NotRequired[int]
    link_connected: NotRequired[bool]
    link_speed: NotRequired[int]
    interface_speed: NotRequired[int]
    accept_ra: NotRequired[bool]


class MemberLinkState(TypedDict):
    """Per-member link state returned on create_bond / create_bridge."""

    id: NotRequired[int | None]
    name: NotRequired[str | None]
    link_connected: NotRequired[bool]


class BondInterface(TypedDict):
    """MAAS bond interface record.

    Python 3.11 TypedDicts do not support real inheritance, so the common
    ``Interface`` fields are redeclared here explicitly. Keep these in sync
    with the canonical ``Interface`` schema above.
    """

    id: int
    name: NotRequired[str | None]
    type: NotRequired[str]
    mac_address: NotRequired[str | None]
    vlan_id: NotRequired[int | None]
    vlan: NotRequired[VlanRef | None]
    parents: NotRequired[list[int]]
    children: NotRequired[list[int]]
    ip_addresses: NotRequired[list[str]]
    links: NotRequired[list[dict[str, Any]]]
    tags: NotRequired[list[str]]
    mtu: NotRequired[int]
    link_connected: NotRequired[bool]
    link_speed: NotRequired[int]
    interface_speed: NotRequired[int]
    accept_ra: NotRequired[bool]
    bond_mode: NotRequired[str]
    bond_downdelay: NotRequired[int]
    bond_lacp_rate: NotRequired[str]
    bond_miimon: NotRequired[int]
    bond_num_grat_arp: NotRequired[int]
    bond_updelay: NotRequired[int]
    bond_xmit_hash_policy: NotRequired[str]
    link_state_classification: NotRequired[str]
    member_link_states: NotRequired[list[MemberLinkState]]


class BridgeInterface(TypedDict):
    """MAAS bridge interface record.

    See ``BondInterface`` for the note about TypedDict composition.
    """

    id: int
    name: NotRequired[str | None]
    type: NotRequired[str]
    mac_address: NotRequired[str | None]
    vlan_id: NotRequired[int | None]
    vlan: NotRequired[VlanRef | None]
    parents: NotRequired[list[int]]
    children: NotRequired[list[int]]
    ip_addresses: NotRequired[list[str]]
    links: NotRequired[list[dict[str, Any]]]
    tags: NotRequired[list[str]]
    mtu: NotRequired[int]
    link_connected: NotRequired[bool]
    link_speed: NotRequired[int]
    interface_speed: NotRequired[int]
    accept_ra: NotRequired[bool]
    link_state_classification: NotRequired[str]
    member_link_states: NotRequired[list[MemberLinkState]]


class IpAddress(TypedDict):
    """Reserved/released IP address record."""

    ip: NotRequired[str]
    subnet: NotRequired[str | int | dict[str, Any]]
    hostname: NotRequired[str | None]
    mac: NotRequired[str | None]
    owner: NotRequired[str | None]
    type: NotRequired[str]
    created: NotRequired[str]
    updated: NotRequired[str]


__all__ = [
    "BondInterface",
    "BridgeInterface",
    "Fabric",
    "Interface",
    "IpAddress",
    "IpRange",
    "MemberLinkState",
    "Space",
    "Subnet",
    "Vlan",
]
