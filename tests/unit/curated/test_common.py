"""Integration: every curated Tool class loads into MCPServer cleanly.

This is the tool-registration gate: it verifies that all tools in
:mod:`maasmcp.curated._common.ALL_TOOLS` can be registered and rebound without
errors. It catches:
  - circular imports introduced by adding new modules
  - duplicate tool name registrations
  - any class that breaks MCPServer's introspection (bad Annotated usage,
    non-callable `run`, etc.)
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from maasmcp.curated._common import register_curated


def test_all_curated_tools_register():
    mcp = MCPServer("test")
    register_curated(mcp)
    # MCPServer stores registered tools in mcp._tool_manager._tools
    tools = mcp._tool_manager._tools  # type: ignore[attr-defined]
    names = sorted(tools.keys())
    # 90 workflow verbs + 36 direct 1:1 MAAS API tools + 1 tools_index helper.
    assert len(names) == 90 + 36 + 1, f"expected 127 tools, got {len(names)}: {names}"
    # Spot-check a few names from each family
    expected_substrings = [
        # v0.4.0 baseline (storage)
        "list_block_devices",
        "create_raid",
        "storage_summary",
        # v0.5.0 networking (this release)
        "list_fabrics",
        "get_fabric",
        "create_fabric",
        "list_spaces",
        "create_space",
        "list_vlans",
        "create_vlan",
        "list_subnets",
        "create_subnet",
        "list_ip_ranges",
        "create_ip_range",
        "list_interfaces",
        "get_interface",
        "create_interface",
        "assign_vlan_to_interface",
        "create_bond",
        "create_bridge",
        "create_interface_vlan",
        "unlink_subnet",
        "network_layout",
        # v0.6.0 composite write
        "apply_storage_layout",
        # v0.6.x fix: link_subnet (was the missing counterpart of unlink_subnet)
        "link_subnet",
        # v0.6.x add: update_interface (wraps PUT /interfaces/{id}/ — used to
        # pre-mark LACP bond members as 10G/connected and to clear a VLAN)
        "update_interface",
        # v0.6.x add: clear_boot_disk (gap-closure tool — returns structured
        # MAAS-limitation data + workarounds instead of issuing a fake call)
        "clear_boot_disk",
        # v0.7.0 direct MAAS tools (one-per-op, hand-written)
        "machines_read",
        "machine_commission",
        "machine_delete",
        "tags_create",
        "users_create",
        "user_delete",
        "fabrics_read",
        # v0.9.0 IP-address lifecycle (from live provisioning: unlinking a
        # link leaves a stale reservation that blocks relinking)
        "ip_addresses_read",
        "ip_address_reserve",
        "ip_address_release",
        # v0.10.0 zone CRUD + mount symmetry
        "zones_list",
        "zones_create",
        "zone_read",
        "zone_update",
        "zone_delete",
        "unmount_block_device",
    ]
    for name in expected_substrings:
        assert name in names, f"missing tool: {name}"


def test_no_duplicate_names():
    mcp = MCPServer("test")
    register_curated(mcp)
    tools = mcp._tool_manager._tools  # type: ignore[attr-defined]
    names = list(tools.keys())
    assert len(names) == len(set(names)), f"duplicate tool names: {names}"
