"""Shared helpers for curated verbs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast, get_args, get_type_hints

from mcp.server.mcpserver import MCPServer
from typing_extensions import is_typeddict

from maasmcp.curated import _catalog
from maasmcp.curated.acquire_machine import AcquireMachineTool
from maasmcp.curated.apply_storage_layout import ApplyStorageLayoutTool
from maasmcp.curated.assign_vlan_to_interface import AssignVlanToInterfaceTool
from maasmcp.curated.bulk_power_control_machines import BulkPowerControlMachinesTool
from maasmcp.curated.bulk_release_machines import BulkReleaseMachinesTool
from maasmcp.curated.bulk_tag_machines import BulkTagMachinesTool
from maasmcp.curated.bulk_untag_machines import BulkUntagMachinesTool
from maasmcp.curated.clear_boot_disk import ClearBootDiskTool
from maasmcp.curated.configure_link import ConfigureLinkTool
from maasmcp.curated.create_block_device import CreateBlockDeviceTool
from maasmcp.curated.create_bond import CreateBondTool
from maasmcp.curated.create_bridge import CreateBridgeTool
from maasmcp.curated.create_fabric import CreateFabricTool
from maasmcp.curated.create_interface import CreateInterfaceTool
from maasmcp.curated.create_interface_vlan import CreateInterfaceVlanTool
from maasmcp.curated.create_ip_range import CreateIpRangeTool
from maasmcp.curated.create_logical_volume import CreateLogicalVolumeTool
from maasmcp.curated.create_partition import CreatePartitionTool
from maasmcp.curated.create_raid import CreateRaidTool
from maasmcp.curated.create_space import CreateSpaceTool
from maasmcp.curated.create_subnet import CreateSubnetTool
from maasmcp.curated.create_vlan import CreateVlanTool
from maasmcp.curated.create_volume_group import CreateVolumeGroupTool
from maasmcp.curated.delete_block_device import DeleteBlockDeviceTool
from maasmcp.curated.delete_fabric import DeleteFabricTool
from maasmcp.curated.delete_interface import DeleteInterfaceTool
from maasmcp.curated.delete_ip_range import DeleteIpRangeTool
from maasmcp.curated.delete_logical_volume import DeleteLogicalVolumeTool
from maasmcp.curated.delete_partition import DeletePartitionTool
from maasmcp.curated.delete_raid import DeleteRaidTool
from maasmcp.curated.delete_space import DeleteSpaceTool
from maasmcp.curated.delete_subnet import DeleteSubnetTool
from maasmcp.curated.delete_vlan import DeleteVlanTool
from maasmcp.curated.delete_volume_group import DeleteVolumeGroupTool
from maasmcp.curated.deploy_machine import DeployMachineTool

# Direct 1:1 MAAS API tools (hand-written since v0.7.0; previously generated
# from the /describe/ snapshot). Exact names preserved for client compat.
from maasmcp.curated.fabrics_read import FabricsReadTool
from maasmcp.curated.find_available_machines import FindAvailableMachinesTool
from maasmcp.curated.format_block_device import FormatBlockDeviceTool
from maasmcp.curated.format_partition import FormatPartitionTool
from maasmcp.curated.get_block_device import GetBlockDeviceTool
from maasmcp.curated.get_fabric import GetFabricTool
from maasmcp.curated.get_interface import GetInterfaceTool
from maasmcp.curated.get_ip_range import GetIpRangeTool
from maasmcp.curated.get_machine import GetMachineTool
from maasmcp.curated.get_partition import GetPartitionTool
from maasmcp.curated.get_raid import GetRaidTool
from maasmcp.curated.get_space import GetSpaceTool
from maasmcp.curated.get_subnet import GetSubnetTool
from maasmcp.curated.get_vlan import GetVlanTool
from maasmcp.curated.get_volume_group import GetVolumeGroupTool
from maasmcp.curated.ip_address_release import IpAddressReleaseTool
from maasmcp.curated.ip_address_reserve import IpAddressReserveTool
from maasmcp.curated.ip_addresses_read import IpAddressesReadTool
from maasmcp.curated.ipranges_read import IprangesReadTool
from maasmcp.curated.link_subnet import LinkSubnetTool
from maasmcp.curated.list_block_devices import ListBlockDevicesTool
from maasmcp.curated.list_fabrics import ListFabricsTool
from maasmcp.curated.list_interfaces import ListInterfacesTool
from maasmcp.curated.list_ip_ranges import ListIpRangesTool
from maasmcp.curated.list_machines import ListMachinesTool
from maasmcp.curated.list_partitions import ListPartitionsTool
from maasmcp.curated.list_raids import ListRaidsTool
from maasmcp.curated.list_spaces import ListSpacesTool
from maasmcp.curated.list_subnets import ListSubnetsTool
from maasmcp.curated.list_vlans import ListVlansTool
from maasmcp.curated.list_volume_groups import ListVolumeGroupsTool
from maasmcp.curated.machine_abort import MachineAbortTool
from maasmcp.curated.machine_commission import MachineCommissionTool
from maasmcp.curated.machine_delete import MachineDeleteTool
from maasmcp.curated.machine_details import MachineDetailsTool
from maasmcp.curated.machine_lock import MachineLockTool
from maasmcp.curated.machine_mark_broken import MachineMarkBrokenTool
from maasmcp.curated.machine_mark_fixed import MachineMarkFixedTool
from maasmcp.curated.machine_power_parameters import MachinePowerParametersTool
from maasmcp.curated.machine_unlock import MachineUnlockTool
from maasmcp.curated.machine_update import MachineUpdateTool
from maasmcp.curated.machines_accept import MachinesAcceptTool
from maasmcp.curated.machines_create import MachinesCreateTool
from maasmcp.curated.machines_is_registered import MachinesIsRegisteredTool
from maasmcp.curated.machines_list_allocated import MachinesListAllocatedTool
from maasmcp.curated.machines_power_parameters import MachinesPowerParametersTool
from maasmcp.curated.machines_read import MachinesReadTool
from maasmcp.curated.machines_set_zone import MachinesSetZoneTool
from maasmcp.curated.mount_block_device import MountBlockDeviceTool
from maasmcp.curated.mount_partition import MountPartitionTool
from maasmcp.curated.network_layout import NetworkLayoutTool
from maasmcp.curated.power_control import PowerControlTool
from maasmcp.curated.power_status import PowerStatusTool
from maasmcp.curated.release_machine import ReleaseMachineTool
from maasmcp.curated.set_boot_disk import SetBootDiskTool
from maasmcp.curated.spaces_read import SpacesReadTool
from maasmcp.curated.storage_summary import StorageSummaryTool
from maasmcp.curated.subnets_read import SubnetsReadTool
from maasmcp.curated.summary import SummaryTool
from maasmcp.curated.tag_delete import TagDeleteTool
from maasmcp.curated.tag_machine import TagMachineTool
from maasmcp.curated.tag_read import TagReadTool
from maasmcp.curated.tag_update import TagUpdateTool
from maasmcp.curated.tags_create import TagsCreateTool
from maasmcp.curated.tags_list import TagsListTool
from maasmcp.curated.tags_read import TagsReadTool
from maasmcp.curated.tools_index import ToolsIndexTool
from maasmcp.curated.unlink_subnet import UnlinkSubnetTool
from maasmcp.curated.unmount_block_device import UnmountBlockDeviceTool
from maasmcp.curated.unmount_partition import UnmountPartitionTool
from maasmcp.curated.untag_machine import UntagMachineTool
from maasmcp.curated.update_block_device import UpdateBlockDeviceTool
from maasmcp.curated.update_fabric import UpdateFabricTool
from maasmcp.curated.update_interface import UpdateInterfaceTool
from maasmcp.curated.update_ip_range import UpdateIpRangeTool
from maasmcp.curated.update_raid import UpdateRaidTool
from maasmcp.curated.update_space import UpdateSpaceTool
from maasmcp.curated.update_subnet import UpdateSubnetTool
from maasmcp.curated.update_vlan import UpdateVlanTool
from maasmcp.curated.update_volume_group import UpdateVolumeGroupTool
from maasmcp.curated.user_delete import UserDeleteTool
from maasmcp.curated.user_read import UserReadTool
from maasmcp.curated.users_create import UsersCreateTool
from maasmcp.curated.users_list import UsersListTool
from maasmcp.curated.users_read import UsersReadTool
from maasmcp.curated.vlans_read import VlansReadTool
from maasmcp.curated.wait_for_state import WaitForStateTool
from maasmcp.curated.zone_delete import ZoneDeleteTool
from maasmcp.curated.zone_read import ZoneReadTool
from maasmcp.curated.zone_update import ZoneUpdateTool
from maasmcp.curated.zones_create import ZonesCreateTool
from maasmcp.curated.zones_list import ZonesListTool

ALL_TOOLS: tuple[type, ...] = (
    # Reads (no gate)
    ListMachinesTool,
    GetMachineTool,
    ListBlockDevicesTool,
    GetBlockDeviceTool,
    ListPartitionsTool,
    GetPartitionTool,
    ListRaidsTool,
    GetRaidTool,
    ListVolumeGroupsTool,
    GetVolumeGroupTool,
    PowerStatusTool,
    SummaryTool,
    StorageSummaryTool,
    FindAvailableMachinesTool,
    # Block-device writes (confirm-gated)
    CreateBlockDeviceTool,
    UpdateBlockDeviceTool,
    DeleteBlockDeviceTool,
    SetBootDiskTool,
    ClearBootDiskTool,
    FormatBlockDeviceTool,
    MountBlockDeviceTool,
    UnmountBlockDeviceTool,
    # Partition writes (confirm-gated)
    CreatePartitionTool,
    DeletePartitionTool,
    FormatPartitionTool,
    MountPartitionTool,
    UnmountPartitionTool,
    # RAID writes (v0.4.0, confirm-gated)
    CreateRaidTool,
    UpdateRaidTool,
    DeleteRaidTool,
    # Volume-group writes (v0.4.0, confirm-gated)
    CreateVolumeGroupTool,
    UpdateVolumeGroupTool,
    DeleteVolumeGroupTool,
    # Logical-volume writes (v0.4.0, confirm-gated, write-only)
    CreateLogicalVolumeTool,
    DeleteLogicalVolumeTool,
    # Bulk fleet operations (v0.2.0, confirm-gated)
    BulkReleaseMachinesTool,
    BulkTagMachinesTool,
    BulkUntagMachinesTool,
    BulkPowerControlMachinesTool,
    # Fabric (v0.5.0)
    ListFabricsTool,
    GetFabricTool,
    CreateFabricTool,
    UpdateFabricTool,
    DeleteFabricTool,
    # Space (v0.5.0)
    ListSpacesTool,
    GetSpaceTool,
    CreateSpaceTool,
    UpdateSpaceTool,
    DeleteSpaceTool,
    # VLAN (v0.5.0)
    ListVlansTool,
    GetVlanTool,
    CreateVlanTool,
    UpdateVlanTool,
    DeleteVlanTool,
    # Subnet (v0.5.0)
    ListSubnetsTool,
    GetSubnetTool,
    CreateSubnetTool,
    UpdateSubnetTool,
    DeleteSubnetTool,
    # IP Range (v0.5.0)
    ListIpRangesTool,
    GetIpRangeTool,
    CreateIpRangeTool,
    UpdateIpRangeTool,
    DeleteIpRangeTool,
    # Interface (v0.5.0)
    ListInterfacesTool,
    GetInterfaceTool,
    CreateInterfaceTool,
    DeleteInterfaceTool,
    AssignVlanToInterfaceTool,
    CreateBondTool,
    CreateBridgeTool,
    CreateInterfaceVlanTool,
    LinkSubnetTool,
    UnlinkSubnetTool,
    UpdateInterfaceTool,
    # One-call DOWN-link repair (composite: connect + speed + VLAN)
    ConfigureLinkTool,
    # Composite read (v0.5.0)
    NetworkLayoutTool,
    # Composite writes (v0.6.0, confirm-gated)
    ApplyStorageLayoutTool,
    # State change + machine lifecycle (all confirm-gated except
    # wait_for_state, which is read-only polling)
    AcquireMachineTool,
    PowerControlTool,
    WaitForStateTool,
    ReleaseMachineTool,
    DeployMachineTool,
    # Single-host tag ops (state-mutating, confirm-gated)
    TagMachineTool,
    UntagMachineTool,
    # Direct MAAS API tools — machine ops
    MachineAbortTool,
    MachineCommissionTool,
    MachineDeleteTool,
    MachineDetailsTool,
    MachineLockTool,
    MachineMarkBrokenTool,
    MachineMarkFixedTool,
    MachinePowerParametersTool,
    MachineUnlockTool,
    MachineUpdateTool,
    MachinesAcceptTool,
    MachinesCreateTool,
    MachinesIsRegisteredTool,
    MachinesListAllocatedTool,
    MachinesPowerParametersTool,
    MachinesReadTool,
    MachinesSetZoneTool,
    # Direct reads — collection endpoints
    FabricsReadTool,
    SpacesReadTool,
    SubnetsReadTool,
    VlansReadTool,
    IpAddressReleaseTool,
    IpAddressReserveTool,
    IpAddressesReadTool,
    IprangesReadTool,
    # Direct tag + user admin
    TagDeleteTool,
    TagReadTool,
    TagUpdateTool,
    TagsCreateTool,
    TagsListTool,
    TagsReadTool,
    UserDeleteTool,
    UserReadTool,
    UsersCreateTool,
    UsersListTool,
    UsersReadTool,
    # Zone CRUD (v0.10.0)
    ZonesListTool,
    ZonesCreateTool,
    ZoneReadTool,
    ZoneUpdateTool,
    ZoneDeleteTool,
    # Discoverability
    ToolsIndexTool,
)

# Pre-computed catalog: avoids recomputing domain/annotations at call time and
# removes the need for tools_index to import ALL_TOOLS lazily.
TOOL_INDEX = _catalog.build_index(cast(tuple[type[_catalog.ToolLike], ...], ALL_TOOLS))


def _return_mentions_typeddict(annotation: Any) -> bool:
    """True when a (possibly generic) annotation contains a TypedDict.

    MCP SDK's ``func_metadata`` tries to build a pydantic output model for
    structured tool output; TypedDict-based schemas can't be modeled that
    way, so the SDK logs a "Cannot create schema" warning per tool at
    registration time. Those tools register with ``structured_output=False``
    instead — the wire result is identical (unstructured JSON text), the
    warning is skipped.
    """
    if annotation is None:
        return False
    if isinstance(annotation, type) and is_typeddict(annotation):
        return True
    return any(_return_mentions_typeddict(arg) for arg in get_args(annotation))


def _uses_typeddict_output(fn: Callable[..., Any]) -> bool:
    """True when ``fn``'s return annotation is (or contains) a TypedDict."""
    try:
        hints = get_type_hints(fn)
    except Exception:  # unresolved forward refs — leave structured output on
        return False
    return _return_mentions_typeddict(hints.get("return"))


def register_curated(mcp: MCPServer) -> None:
    """Register every curated tool on ``mcp`` with enriched metadata."""
    for cls in ALL_TOOLS:
        instance = cls()
        name = instance.name
        domain = _catalog.domain_for(name)
        annotations = _catalog.infer_annotations(name)
        description = f"[{domain}] {instance.description}"
        mcp.add_tool(
            instance.run,
            name=name,
            title=annotations.title,
            description=description,
            annotations=annotations,
            structured_output=False if _uses_typeddict_output(instance.run) else None,
        )
