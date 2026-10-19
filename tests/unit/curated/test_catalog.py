"""Unit tests for the tool catalog metadata helpers."""

from __future__ import annotations

import pytest

from maasmcp.curated._catalog import (
    DESTRUCTIVE_NAMES,
    READ_ONLY_NAMES,
    build_index,
    domain_for,
    infer_annotations,
    title_for,
)
from maasmcp.curated.create_fabric import CreateFabricTool
from maasmcp.curated.delete_block_device import DeleteBlockDeviceTool
from maasmcp.curated.list_machines import ListMachinesTool
from maasmcp.curated.power_control import PowerControlTool
from maasmcp.curated.tools_index import ToolsIndexTool


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("list_machines", "machines"),
        ("delete_block_device", "storage"),
        ("create_fabric", "network"),
        ("create_bond", "network"),
        ("assign_vlan_to_interface", "network"),
        ("tag_machine", "tags"),
        ("users_create", "users"),
        ("zones_list", "zones"),
        ("bulk_release_machines", "fleet"),
        ("tools_index", "meta"),
        ("summary", "system"),
        ("fabrics_read", "network"),
        ("spaces_read", "network"),
        ("subnets_read", "network"),
        ("vlans_read", "network"),
    ],
)
def test_domain_for(name: str, expected: str) -> None:
    assert domain_for(name) == expected


def test_domain_for_unknown_returns_misc() -> None:
    assert domain_for("unknown_tool") == "misc"


def test_title_for_snake_case() -> None:
    assert title_for("list_machines") == "List Machines"


def test_infer_annotations_read_tool() -> None:
    ann = infer_annotations("list_machines")
    assert ann.read_only_hint is True
    assert ann.destructive_hint is False
    assert ann.idempotent_hint is True
    assert ann.title == "List Machines"


def test_infer_annotations_destructive_write() -> None:
    ann = infer_annotations("delete_block_device")
    assert ann.read_only_hint is False
    assert ann.destructive_hint is True
    assert ann.idempotent_hint is False


def test_infer_annotations_write_tool() -> None:
    ann = infer_annotations("create_fabric")
    assert ann.read_only_hint is False
    assert ann.destructive_hint is True
    assert ann.idempotent_hint is False


def test_infer_annotations_update_write() -> None:
    ann = infer_annotations("update_block_device")
    assert ann.read_only_hint is False
    assert ann.destructive_hint is True
    assert ann.idempotent_hint is False


def test_infer_annotations_explicit_destructive_name() -> None:
    for name in DESTRUCTIVE_NAMES:
        ann = infer_annotations(name)
        assert ann.destructive_hint is True, name


def test_infer_annotations_explicit_read_name() -> None:
    for name in READ_ONLY_NAMES:
        ann = infer_annotations(name)
        assert ann.read_only_hint is True, name


@pytest.mark.parametrize(
    "name",
    ["users_list", "tags_list", "zones_list"],
)
def test_infer_annotations_plural_list_tools_are_read_only(name: str) -> None:
    ann = infer_annotations(name)
    assert ann.read_only_hint is True, name
    assert ann.destructive_hint is False, name
    assert ann.idempotent_hint is True, name


def test_build_index_groups_tools() -> None:
    response = build_index(
        (
            ListMachinesTool,
            DeleteBlockDeviceTool,
            CreateFabricTool,
            PowerControlTool,
            ToolsIndexTool,
        )
    )
    groups = response.groups
    assert set(groups.keys()) == {"machines", "storage", "network", "meta"}
    assert any(entry.name == "list_machines" for entry in groups["machines"])
    assert any(entry.name == "delete_block_device" for entry in groups["storage"])
    assert any(entry.name == "tools_index" for entry in groups["meta"])


def test_no_curated_tool_in_misc_domain() -> None:
    """Every real tool must map to a meaningful domain; misc is a fallback."""
    from maasmcp.curated._common import ALL_TOOLS

    misc = [cls.name for cls in ALL_TOOLS if domain_for(cls.name) == "misc"]
    assert not misc, f"tools in misc domain: {misc}"
