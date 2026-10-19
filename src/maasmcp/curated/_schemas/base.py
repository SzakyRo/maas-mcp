"""Shared TypedDict schemas used by multiple curated tool domains.

These types are intentionally loose (``NotRequired`` for optional fields) because
they describe the shape the tool *returns*, not a validation envelope. MAAS may
omit fields depending on the endpoint and version, so runtime code still does
best-effort extraction.
"""

from __future__ import annotations

from typing import NotRequired

from typing_extensions import TypedDict


class MachineSlim(TypedDict):
    """Lightweight machine view used by list_machines and find_available_machines."""

    system_id: str | None
    hostname: str | None
    status_name: NotRequired[str | None]
    power_state: NotRequired[str | None]
    tag_names: NotRequired[list[str]]
    pool: NotRequired[str | None]


class MachineNormalized(TypedDict):
    """Normalized machine record returned by get_machine."""

    system_id: str | None
    hostname: str | None
    tag_names: NotRequired[list[str]]
    pool: NotRequired[str | None]
    owner: NotRequired[str | None]
    power_state: NotRequired[str | None]
    os: NotRequired[str]
    last_commissioned: NotRequired[str | None]
    boot_disk_id: NotRequired[int | None]
    boot_disk_name: NotRequired[str | None]


class FleetSummary(TypedDict):
    """Fleet-wide summary returned by summary."""

    by_status: dict[str, int]
    by_pool: dict[str, int]
    by_zone: dict[str, int]
    total_memory_mb: int
    total_cpu_count: int
    machine_count: int
    pod_count: int
    pod_count_by_status: dict[str, int]


class StorageSummary(TypedDict):
    """Cross-resource storage summary returned by storage_summary."""

    system_id: str
    block_devices: int
    partitions: int
    total_size_gib: float
    raid_devices: int
    volume_groups: int
    logical_volumes: int


class VlanRef(TypedDict):
    """Minimal VLAN reference."""

    id: int
    name: NotRequired[str | None]
    vid: NotRequired[int]
    fabric_id: NotRequired[int]


class LinkedSubnet(TypedDict):
    """Minimal subnet reference attached to an interface in network_layout."""

    id: NotRequired[int]
    cidr: NotRequired[str]
    gateway_ip: NotRequired[str | None]


class NetworkInterface(TypedDict):
    """Joined interface record returned by network_layout."""

    id: NotRequired[int]
    name: NotRequired[str]
    type: NotRequired[str]
    mac_address: NotRequired[str]
    vlan: NotRequired[VlanRef | None]
    linked_subnet: NotRequired[LinkedSubnet | None]
    parents: NotRequired[list[int]]
    children: NotRequired[list[int]]
    ip_addresses: NotRequired[list[str]]


class NetworkLayout(TypedDict):
    """Composite network topology returned by network_layout."""

    system_id: str
    fabric_count: int
    vlan_count: int
    subnet_count: int
    interface_count: int
    ip_range_count: int
    interfaces: list[NetworkInterface]
    partial: bool
    errors: list[str]
    fabric_vlan_counts: dict[int, int]


__all__ = [
    "FleetSummary",
    "LinkedSubnet",
    "MachineNormalized",
    "MachineSlim",
    "NetworkInterface",
    "NetworkLayout",
    "StorageSummary",
    "VlanRef",
]
