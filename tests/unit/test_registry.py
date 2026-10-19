"""Registry completeness: the registry module must expose the full expected tool set.

Guards against a tool silently dropping out of registration (bad import,
missing entry in register_curated, rebinding failure) and against duplicate
names. Coarse-grained on purpose: it pins the *set* of registered names, so
adding a tool requires listing it here — the PR diff then shows the surface
change explicitly.
"""

from __future__ import annotations

# Read-only workflow verbs and composite reads.
CURATED_READS = {
    "list_machines",
    "get_machine",
    "list_block_devices",
    "get_block_device",
    "list_partitions",
    "get_partition",
    "list_raids",
    "get_raid",
    "list_volume_groups",
    "get_volume_group",
    "power_status",
    "summary",
    "storage_summary",
    "find_available_machines",
    "list_fabrics",
    "get_fabric",
    "list_spaces",
    "get_space",
    "list_vlans",
    "get_vlan",
    "list_subnets",
    "get_subnet",
    "list_ip_ranges",
    "get_ip_range",
    "list_interfaces",
    "get_interface",
    "network_layout",
    "wait_for_state",
    "ip_addresses_read",
    "zones_list",
    "zone_read",
    "tools_index",
}

# Gated workflow verbs (writes and state-mutating allocations).
CURATED_WRITES = {
    "ip_address_release",
    "ip_address_reserve",
    "acquire_machine",
    "create_block_device",
    "update_block_device",
    "delete_block_device",
    "set_boot_disk",
    "clear_boot_disk",
    "format_block_device",
    "mount_block_device",
    "create_partition",
    "delete_partition",
    "format_partition",
    "mount_partition",
    "unmount_partition",
    "create_raid",
    "update_raid",
    "delete_raid",
    "create_volume_group",
    "update_volume_group",
    "delete_volume_group",
    "create_logical_volume",
    "delete_logical_volume",
    "bulk_release_machines",
    "bulk_tag_machines",
    "bulk_untag_machines",
    "bulk_power_control_machines",
    "create_fabric",
    "update_fabric",
    "delete_fabric",
    "create_space",
    "update_space",
    "delete_space",
    "create_vlan",
    "update_vlan",
    "delete_vlan",
    "create_subnet",
    "update_subnet",
    "delete_subnet",
    "create_ip_range",
    "update_ip_range",
    "delete_ip_range",
    "create_interface",
    "delete_interface",
    "assign_vlan_to_interface",
    "create_bond",
    "create_bridge",
    "create_interface_vlan",
    "link_subnet",
    "unlink_subnet",
    "update_interface",
    "configure_link",
    "apply_storage_layout",
    "power_control",
    "release_machine",
    "deploy_machine",
    "tag_machine",
    "untag_machine",
    "unmount_block_device",
    "zones_create",
    "zone_update",
    "zone_delete",
}

# Direct 1:1 MAAS API tools (formerly the generated layer).
DIRECT_TOOLS = {
    "machine_abort",
    "machine_commission",
    "machine_delete",
    "machine_details",
    "machine_lock",
    "machine_mark_broken",
    "machine_mark_fixed",
    "machine_power_parameters",
    "machine_unlock",
    "machine_update",
    "machines_accept",
    "machines_create",
    "machines_is_registered",
    "machines_list_allocated",
    "machines_power_parameters",
    "machines_read",
    "machines_set_zone",
    "fabrics_read",
    "spaces_read",
    "subnets_read",
    "vlans_read",
    "ipranges_read",
    "ip_addresses_read",
    "ip_address_reserve",
    "ip_address_release",
    "tag_delete",
    "tag_read",
    "tag_update",
    "tags_create",
    "tags_list",
    "tags_read",
    "user_delete",
    "user_read",
    "users_create",
    "users_list",
    "users_read",
}

EXPECTED = CURATED_READS | CURATED_WRITES | DIRECT_TOOLS


def _registered_names() -> set[str]:
    from maasmcp.registry import mcp

    return set(mcp._tool_manager._tools.keys())


def test_all_expected_tools_registered() -> None:
    names = _registered_names()
    missing = EXPECTED - names
    assert not missing, f"missing tools: {sorted(missing)}"


def test_no_unexpected_or_duplicate_tools() -> None:
    names = _registered_names()
    extra = names - EXPECTED
    assert not extra, f"unexpected tools: {sorted(extra)}"
    assert len(names) == len(EXPECTED)


def test_no_tool_publishes_client_param() -> None:
    """After rebinding, no published JSON schema may expose the client param."""
    from maasmcp.registry import mcp

    for tool in mcp._tool_manager._tools.values():
        props = tool.parameters.get("properties", {})
        assert "client" not in props, f"{tool.name} still publishes a client param"


def test_reads_writes_split_matches_confirm_gate() -> None:
    """The READS/WRITES pin lists are enforced, not just documentation.

    Every pinned CURATED_READS tool must NOT expose a ``confirm`` param;
    every pinned CURATED_WRITES tool must expose one (and per the project
    standard, its gate must raise before any MAAS call — covered by the
    per-tool rejection tests).
    """
    from maasmcp.registry import mcp

    tools = mcp._tool_manager._tools
    for name, tool in tools.items():
        has_confirm = "confirm" in tool.parameters.get("properties", {})
        if name in CURATED_READS:
            assert not has_confirm, f"{name} is pinned as a read but exposes confirm"
        elif name in CURATED_WRITES:
            assert has_confirm, f"{name} is pinned as a write but has no confirm gate"


def test_all_tools_have_title_and_annotations() -> None:
    from maasmcp.registry import mcp

    for tool in mcp._tool_manager._tools.values():
        assert tool.title, f"{tool.name} missing title"
        assert tool.annotations is not None, f"{tool.name} missing annotations"
        assert tool.annotations.read_only_hint is not None
        assert tool.annotations.destructive_hint is not None
        assert not (tool.annotations.read_only_hint and tool.annotations.destructive_hint), (
            f"{tool.name} is both read-only and destructive"
        )
        assert not (tool.annotations.idempotent_hint and tool.annotations.destructive_hint), (
            f"{tool.name} is both idempotent and destructive"
        )


def test_all_descriptions_have_domain_tag() -> None:
    from maasmcp.curated._catalog import domain_for
    from maasmcp.registry import mcp

    for tool in mcp._tool_manager._tools.values():
        assert tool.description.startswith("["), f"{tool.name} missing domain tag"
        tag = tool.description.split("]", 1)[0][1:]
        assert tag == domain_for(tool.name), f"{tool.name} domain tag mismatch"


def test_machine_addressing_params_are_paired_with_hostname() -> None:
    """Registry guard: every machine-addressed tool must accept both id forms.

    Ensures no tool with system_id/system_ids/nodes/machines params is missing
    their hostname sibling — a backstop for the hostname-addressing migration.
    """
    import inspect

    from maasmcp.curated._common import ALL_TOOLS

    # Param names that must be paired so no machine-addressed tool can silently
    # stay system_id-only. values = the sibling param that must also exist.
    DUAL_ADDRESSING_PAIRS = {
        "system_id": "hostname",
        "system_ids": "hostnames",
        "nodes": "hostname",  # machines_set_zone
        "machines": "hostnames",  # machines_accept
    }

    offenders: dict[str, list[str]] = {}
    for cls in ALL_TOOLS:
        params = inspect.signature(cls().run).parameters
        for source, sibling in DUAL_ADDRESSING_PAIRS.items():
            if source in params and sibling not in params:
                offenders.setdefault(cls.name, []).append(f"{source} lacks {sibling}")
    assert not offenders, (
        "machine-addressed tools missing their hostname sibling: "
        + "; ".join(f"{t}: {', '.join(m)}" for t, m in offenders.items())
    )
