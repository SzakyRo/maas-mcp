"""TypedDict schemas for MAAS storage resources.

These describe the shapes returned by storage curated tools. They are loose
(``NotRequired`` for optional fields) because MAAS may omit fields depending
on endpoint and version; runtime code still does best-effort extraction.
"""

from __future__ import annotations

from typing import Any, NotRequired

from typing_extensions import TypedDict


class Filesystem(TypedDict):
    """Filesystem embedded in block devices or partitions."""

    fstype: NotRequired[str | None]
    uuid: NotRequired[str | None]
    label: NotRequired[str | None]
    mount_point: NotRequired[str | None]


class BlockDevice(TypedDict):
    """MAAS block-device record returned by list/get/create/update."""

    id: int
    name: str
    size: NotRequired[int]
    block_size: NotRequired[int]
    type: NotRequired[str]
    model: NotRequired[str | None]
    serial: NotRequired[str | None]
    id_path: NotRequired[str | None]
    path: NotRequired[str | None]
    uuid: NotRequired[str | None]
    used_size: NotRequired[int]
    available_size: NotRequired[int]
    filesystem: NotRequired[Filesystem | None]
    partition_table_type: NotRequired[str | None]
    partitions: NotRequired[list[Partition]]
    parent: NotRequired[dict[str, Any] | None]
    children: NotRequired[list[dict[str, Any]]]


class Partition(TypedDict):
    """MAAS partition record returned by list/get/create."""

    id: int
    uuid: NotRequired[str | None]
    path: NotRequired[str | None]
    size: NotRequired[int]
    bootable: NotRequired[bool]
    filesystem: NotRequired[Filesystem | None]


class VirtualDevice(TypedDict):
    """RAID virtual block device reference."""

    id: NotRequired[int]
    name: NotRequired[str]
    type: NotRequired[str]


class RaidMemberRef(TypedDict):
    """Reference to a block device or partition member of a RAID."""

    id: NotRequired[int]
    type: NotRequired[str]


class Raid(TypedDict):
    """MAAS RAID array returned by list/get/create/update."""

    id: int
    name: NotRequired[str | None]
    level: NotRequired[str]
    uuid: NotRequired[str | None]
    size: NotRequired[int]
    devices: NotRequired[list[RaidMemberRef]]
    spare_devices: NotRequired[list[RaidMemberRef]]
    virtual_device: NotRequired[VirtualDevice | None]


class LogicalVolume(TypedDict):
    """MAAS logical volume returned by create/list/get volume group."""

    id: NotRequired[int]
    name: NotRequired[str]
    size: NotRequired[int]
    uuid: NotRequired[str | None]


class VolumeGroup(TypedDict):
    """MAAS volume group returned by list/get/create/update."""

    id: int
    name: str
    uuid: NotRequired[str | None]
    size: NotRequired[int]
    logical_volumes: NotRequired[list[LogicalVolume]]
    block_devices: NotRequired[list[BlockDevice | RaidMemberRef]]
    partitions: NotRequired[list[Partition | RaidMemberRef]]


class StatusOperation(TypedDict):
    """Normalized status dict returned by simple CRUD/format/mount operations."""

    status: str
    system_id: str
    resource_id: int
    operation: str


class CurrentBootDisk(TypedDict):
    """Current boot disk reported by clear_boot_disk."""

    boot_disk_id: int | None
    boot_disk_name: str | None
    boot_disk_path: str | None


class Workaround(TypedDict):
    """Workaround entry returned by clear_boot_disk."""

    name: str
    destructive: bool
    description: str
    verbs: list[str]


class ClearBootDiskResult(TypedDict):
    """Result shape returned by clear_boot_disk."""

    status: str
    system_id: str
    operation: str
    reason: str
    current_boot_disk: CurrentBootDisk
    available_workarounds: list[Workaround]


class CompletedStep(TypedDict):
    """One completed step recorded by apply_storage_layout."""

    step: str


class ApplyStorageLayoutResult(TypedDict):
    """Result shape returned by apply_storage_layout."""

    system_id: str
    layout_type: str | None
    status: str
    completed_steps: list[CompletedStep | dict[str, Any]]
    failed_step: dict[str, Any] | None
    errors: list[str]
    rollback_hint: str


__all__ = [
    "ApplyStorageLayoutResult",
    "BlockDevice",
    "ClearBootDiskResult",
    "CompletedStep",
    "CurrentBootDisk",
    "Filesystem",
    "LogicalVolume",
    "Partition",
    "Raid",
    "RaidMemberRef",
    "StatusOperation",
    "VirtualDevice",
    "VolumeGroup",
    "Workaround",
]
