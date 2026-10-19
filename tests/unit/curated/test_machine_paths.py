"""Unit tests for _machine_paths URL helpers."""

import pytest

from maasmcp.curated import _machine_paths as p


def test_machines_path():
    assert p.machines_path() == "/api/2.0/machines/"


def test_machines_op_path():
    assert p.machines_op_path("accept") == "/api/2.0/machines/?op=accept"
    assert p.machines_op_path("set_zone") == "/api/2.0/machines/?op=set_zone"


def test_machine_path():
    assert p.machine_path("abc123") == "/api/2.0/machines/abc123/"


def test_machine_op_path():
    assert p.machine_op_path("abc", "op-power_on") == "/api/2.0/machines/abc/op-power_on"
    assert p.machine_op_path("abc", "op-release") == "/api/2.0/machines/abc/op-release"


def test_machine_query_op_path():
    assert p.machine_query_op_path("abc", "abort") == "/api/2.0/machines/abc/?op=abort"
    assert p.machine_query_op_path("abc", "mark_broken") == "/api/2.0/machines/abc/?op=mark_broken"


def test_machine_paths_reject_unsafe_system_id():
    for bad in ["../x", "a/b", "a?x=1", "a#frag", "a x", ""]:
        with pytest.raises(ValueError, match="system_id"):
            p.machine_path(bad)
        with pytest.raises(ValueError, match="system_id"):
            p.machine_op_path(bad, "op-power_on")
        with pytest.raises(ValueError, match="system_id"):
            p.machine_query_op_path(bad, "abort")
