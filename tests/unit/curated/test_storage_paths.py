"""Unit tests for path templating helpers."""

from __future__ import annotations

import pytest

from maasmcp.curated._storage_paths import (
    lv_create_path,
    lv_delete_path,
    raid_path,
    raids_path,
    volume_group_path,
    volume_groups_path,
)


def test_raids_path() -> None:
    assert raids_path("abc") == "/api/2.0/nodes/abc/raids/"


def test_raid_path() -> None:
    assert raid_path("abc", 7) == "/api/2.0/nodes/abc/raid/7/"


def test_volume_groups_path() -> None:
    assert volume_groups_path("abc") == "/api/2.0/nodes/abc/volume-groups/"


def test_volume_group_path() -> None:
    assert volume_group_path("abc", 3) == "/api/2.0/nodes/abc/volume-group/3/"


def test_lv_create_path() -> None:
    assert lv_create_path("abc", 3) == "/api/2.0/nodes/abc/volume-group/3/op-create_logical_volume"


def test_lv_delete_path() -> None:
    assert lv_delete_path("abc", 3) == "/api/2.0/nodes/abc/volume-group/3/op-delete_logical_volume"


def test_validate_id_rejects_zero():
    from maasmcp.curated._storage_paths import _validate_id

    with pytest.raises(ValueError, match="fabric_id"):
        _validate_id(fabric_id=0)


def test_validate_id_accepts_positive():
    from maasmcp.curated._storage_paths import _validate_id

    _validate_id(fabric_id=1)  # no raise


def test_validate_system_id_rejects_traversal_and_smuggling():
    from maasmcp.curated._storage_paths import validate_system_id

    for bad in ["../x", "a/b", "a?x=1", "a#frag", "a x", "%2e%2e", ""]:
        with pytest.raises(ValueError, match="system_id"):
            validate_system_id(bad)


def test_validate_system_id_accepts_maas_ids():
    from maasmcp.curated._storage_paths import validate_system_id

    validate_system_id("eec43g")
    validate_system_id("8smce7")
    validate_system_id("a-b_c.d~1")


def test_validate_ids_rejects_bad_system_id():
    from maasmcp.curated._storage_paths import _validate_ids

    with pytest.raises(ValueError, match="system_id"):
        _validate_ids("a/b", block_device_id=1)
