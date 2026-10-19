"""Unit tests for _network_paths URL helpers."""

import pytest

from maasmcp.curated import _network_paths as p


def test_fabrics_path():
    assert p.fabrics_path() == "/api/2.0/fabrics/"


def test_fabric_path():
    assert p.fabric_path(7) == "/api/2.0/fabrics/7/"


def test_spaces_path():
    assert p.spaces_path() == "/api/2.0/spaces/"


def test_space_path():
    assert p.space_path(3) == "/api/2.0/spaces/3/"


def test_vlans_path():
    assert p.vlans_path(1) == "/api/2.0/fabrics/1/vlans/"


def test_vlan_path():
    assert p.vlan_path(1, 42) == "/api/2.0/fabrics/1/vlans/42/"


def test_vlan_path_vid_out_of_range():
    # vid=0 is valid: it is the fabric's untagged default VLAN (e.g. for
    # enabling MAAS-managed DHCP via update_vlan primary_rack).
    assert p.vlan_path(1, 0) == "/api/2.0/fabrics/1/vlans/0/"
    with pytest.raises(ValueError, match="vid must be in"):
        p.vlan_path(1, -1)
    with pytest.raises(ValueError, match="vid must be in"):
        p.vlan_path(1, 4095)


def test_subnets_path():
    assert p.subnets_path() == "/api/2.0/subnets/"


def test_subnet_path():
    assert p.subnet_path(99) == "/api/2.0/subnets/99/"


def test_ip_ranges_path():
    assert p.ip_ranges_path() == "/api/2.0/ipranges/"


def test_ip_range_path():
    assert p.ip_range_path(5) == "/api/2.0/ipranges/5/"


def test_interfaces_path():
    assert p.interfaces_path("abc123") == "/api/2.0/nodes/abc123/interfaces/"


def test_interface_path():
    assert p.interface_path("abc123", 8) == "/api/2.0/nodes/abc123/interfaces/8/"


def test_interface_op_path():
    assert (
        p.interface_op_path("abc123", 8, "op-create_bond")
        == "/api/2.0/nodes/abc123/interfaces/8/op-create_bond"
    )


def test_validate_ids_re_exported():
    """Cross-domain re-export: _validate_ids lives in _storage_paths but
    networking verbs import from _network_paths for convenience."""
    from maasmcp.curated._network_paths import _validate_ids
    from maasmcp.curated._storage_paths import _validate_ids as canonical

    assert _validate_ids is canonical


def test_vlan_path_accepts_default_fabric_zero():
    """MAAS's default fabric is fabric-0 — id 0 must be accepted."""
    assert p.vlan_path(0, 42) == "/api/2.0/fabrics/0/vlans/42/"
    assert p.vlans_path(0) == "/api/2.0/fabrics/0/vlans/"
