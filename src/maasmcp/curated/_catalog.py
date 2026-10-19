"""Catalog metadata for curated MCP tools.

Provides domain tags, human-friendly titles, and MCP ``ToolAnnotations`` for
every tool registered in :data:`maasmcp.curated._common.ALL_TOOLS`.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Protocol

from mcp.types import ToolAnnotations
from pydantic import BaseModel


class ToolLike(Protocol):
    """Protocol for classes that can be indexed by ``build_index``."""

    name: str
    description: str


class ToolIndexEntry(BaseModel):
    """One entry in the tools_index response."""

    name: str
    title: str | None
    description: str
    read_only: bool | None
    destructive: bool | None
    idempotent: bool | None


class ToolsIndexResponse(BaseModel):
    """Response shape returned by the ``tools_index`` tool."""

    groups: dict[str, list[ToolIndexEntry]]


DOMAIN_EXACT: dict[str, str] = {
    "tools_index": "meta",
    "summary": "system",
    "storage_summary": "storage",
    "network_layout": "network",
    "find_available_machines": "machines",
    "acquire_machine": "machines",
    "deploy_machine": "machines",
    "release_machine": "machines",
    "power_control": "machines",
    "power_status": "machines",
    "wait_for_state": "machines",
    "machine_details": "machines",
    "machine_power_parameters": "machines",
    "machines_power_parameters": "machines",
    "machines_is_registered": "machines",
    "machines_list_allocated": "machines",
    "apply_storage_layout": "storage",
    "set_boot_disk": "storage",
    "clear_boot_disk": "storage",
    "list_interfaces": "network",
    "get_interface": "network",
    "create_interface": "network",
    "delete_interface": "network",
    "update_interface": "network",
    "configure_link": "network",
    "assign_vlan_to_interface": "network",
    "create_bond": "network",
    "create_bridge": "network",
    "create_interface_vlan": "network",
    "link_subnet": "network",
    "unlink_subnet": "network",
    "ip_address_reserve": "network",
    "ip_address_release": "network",
    "ip_addresses_read": "network",
    "ipranges_read": "network",
    "fabrics_read": "network",
    "spaces_read": "network",
    "subnets_read": "network",
    "vlans_read": "network",
    "bulk_release_machines": "fleet",
    "bulk_tag_machines": "fleet",
    "bulk_untag_machines": "fleet",
    "bulk_power_control_machines": "fleet",
}

DOMAIN_PREFIXES: tuple[tuple[str, str], ...] = (
    ("bulk_", "fleet"),
    ("tag_", "tags"),
    ("tags_", "tags"),
    ("untag_", "tags"),
    ("user_", "users"),
    ("users_", "users"),
    ("zone_", "zones"),
    ("zones_", "zones"),
    ("machine_", "machines"),
    ("machines_", "machines"),
)

ACTION_PREFIXES: tuple[str, ...] = (
    "list_",
    "get_",
    "create_",
    "update_",
    "delete_",
    "find_",
    "format_",
    "mount_",
    "unmount_",
    "assign_",
    "apply_",
    "set_",
    "clear_",
    "link_",
    "unlink_",
    "acquire_",
    "deploy_",
    "release_",
    "power_",
    "wait_",
)

RESOURCE_DOMAINS: tuple[tuple[str, str], ...] = (
    ("block_device", "storage"),
    ("block_devices", "storage"),
    ("partition", "storage"),
    ("partitions", "storage"),
    ("raid", "storage"),
    ("raids", "storage"),
    ("volume_group", "storage"),
    ("volume_groups", "storage"),
    ("logical_volume", "storage"),
    ("logical_volumes", "storage"),
    ("fabric", "network"),
    ("fabrics", "network"),
    ("space", "network"),
    ("spaces", "network"),
    ("vlan", "network"),
    ("vlans", "network"),
    ("subnet", "network"),
    ("subnets", "network"),
    ("ip_range", "network"),
    ("ip_ranges", "network"),
    ("interface", "network"),
    ("interfaces", "network"),
    ("bond", "network"),
    ("bridge", "network"),
    ("machine", "machines"),
    ("machines", "machines"),
    ("summary", "system"),
)

EXPECTED_DOMAINS: frozenset[str] = frozenset(
    set(DOMAIN_EXACT.values())
    | {domain for _, domain in DOMAIN_PREFIXES}
    | {domain for _, domain in RESOURCE_DOMAINS}
)

READ_ONLY_NAMES: frozenset[str] = frozenset(
    {
        "tools_index",
        "summary",
        "storage_summary",
        "network_layout",
        "wait_for_state",
        "find_available_machines",
        "power_status",
        "machine_details",
        "machine_power_parameters",
        "machines_power_parameters",
        "machines_is_registered",
        "machines_list_allocated",
    }
)

DESTRUCTIVE_NAMES: frozenset[str] = frozenset(
    {
        "release_machine",
        "bulk_release_machines",
        "machine_delete",
        "user_delete",
        "tag_delete",
        "zone_delete",
        "apply_storage_layout",
        # Wire-level read (GET only); the destructive hint matches the
        # caller's clear-intent rather than the wire behavior (see docstring).
        "clear_boot_disk",
    }
)


def domain_for(name: str) -> str:
    """Return the domain tag for a tool name."""
    if name in DOMAIN_EXACT:
        return DOMAIN_EXACT[name]
    for prefix, domain in DOMAIN_PREFIXES:
        if name.startswith(prefix):
            return domain
    for action in ACTION_PREFIXES:
        if name.startswith(action):
            base = name[len(action) :]
            for resource, domain in RESOURCE_DOMAINS:
                if base.startswith(resource):
                    return domain
            # Only one action prefix can match; if no resource matched, fall
            # back to misc rather than trying a later action prefix.
            break
    return "misc"


def title_for(name: str) -> str:
    """Convert a snake_case tool name to a Title Case title."""
    return name.replace("_", " ").title()


def infer_annotations(name: str) -> ToolAnnotations:
    """Infer MCP ToolAnnotations from the tool name.

    Read-only tools (lists, gets, reads, summaries, layout) are flagged as
    ``read_only_hint=True`` and ``idempotent_hint=True``. Every other tool is
    treated as a state-mutating write and therefore destructive (the MCP spec
    defines ``destructiveHint`` as true for any tool that may modify its
    environment). Those writes are not idempotent. A small explicit override
    set handles names whose suffix would otherwise look like a read but which
    are actually destructive writes.
    """
    lower = name.lower()

    if name in DESTRUCTIVE_NAMES:
        return ToolAnnotations(
            title=title_for(name),
            read_only_hint=False,
            destructive_hint=True,
            idempotent_hint=False,
            open_world_hint=False,
        )

    is_read = (
        name in READ_ONLY_NAMES
        or lower.startswith(("list_", "get_", "find_"))
        or lower.endswith(("_read", "_summary", "_layout", "_list"))
    )
    if is_read:
        return ToolAnnotations(
            title=title_for(name),
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )

    return ToolAnnotations(
        title=title_for(name),
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        open_world_hint=False,
    )


def _first_sentence(text: str) -> str:
    """Return the first sentence of a description, truncated to 200 chars."""
    sentence = re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)[0]
    if len(sentence) > 200:
        return sentence[:197].rstrip() + "..."
    return sentence


def build_index(tools: tuple[type[ToolLike], ...]) -> ToolsIndexResponse:
    """Build the grouped catalog returned by ``tools_index``."""
    groups: dict[str, list[ToolIndexEntry]] = defaultdict(list)
    for cls in tools:
        name = cls.name
        ann = infer_annotations(name)
        groups[domain_for(name)].append(
            ToolIndexEntry(
                name=name,
                title=ann.title,
                description=_first_sentence(cls.description),
                read_only=ann.read_only_hint,
                destructive=ann.destructive_hint,
                idempotent=ann.idempotent_hint,
            )
        )
    return ToolsIndexResponse(groups=dict(groups))
