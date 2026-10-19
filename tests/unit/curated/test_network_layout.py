"""Tests for NetworkLayoutTool — including the hostname→system_id resolution path."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.config import MaasmcpConfig
from maasmcp.curated.network_layout import NetworkLayoutTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


async def test_network_layout_empty_machine(monkeypatch):
    """Machine with no interfaces returns zero counts and empty list."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.get("/api/2.0/nodes/abc123/interfaces/").mock(
            return_value=Response(200, json={"interfaces": []})
        )
        mock.get("/api/2.0/subnets/").mock(return_value=Response(200, json={"subnets": []}))
        async with maas_client:
            result = await NetworkLayoutTool().run(maas_client, system_id="abc123")
    assert result["system_id"] == "abc123"
    assert result["interface_count"] == 0
    assert result["fabric_count"] == 0
    assert result["vlan_count"] == 0
    assert result["subnet_count"] == 0
    assert result["ip_range_count"] == 0
    assert result["interfaces"] == []
    assert result["partial"] is False
    assert result["errors"] == []


async def test_network_layout_single_interface_with_vlan(monkeypatch):
    """One physical interface on VLAN 100 on fabric 1.

    Stage-1 subnet response embeds `vlan: {vid, id, fabric}` so the tool can
    build the fabric-scoped VLAN URL for Stage 2.
    """
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.get("/api/2.0/nodes/abc123/interfaces/").mock(
            return_value=Response(
                200,
                json={
                    "interfaces": [
                        {
                            "id": 8,
                            "name": "eth0",
                            "type": "physical",
                            "mac_address": "00:11:22:33:44:55",
                            "vlan_id": 100,
                            "parents": [],
                            "ip_addresses": ["10.0.0.5"],
                        },
                    ],
                },
            )
        )
        mock.get("/api/2.0/subnets/").mock(
            return_value=Response(
                200,
                json={
                    "subnets": [
                        {
                            "id": 5,
                            "cidr": "10.0.0.0/24",
                            "vlan": {"vid": 100, "id": 100, "fabric": "fabric-1", "fabric_id": 1},
                            "gateway_ip": "10.0.0.1",
                        }
                    ]
                },
            )
        )
        mock.get("/api/2.0/fabrics/1/vlans/100/").mock(
            return_value=Response(
                200,
                json={"id": 100, "vid": 100, "name": "v100", "fabric": "fabric-1", "fabric_id": 1},
            )
        )
        async with maas_client:
            result = await NetworkLayoutTool().run(maas_client, system_id="abc123")
    assert result["interface_count"] == 1
    assert result["fabric_count"] == 1
    assert result["vlan_count"] == 1
    assert result["subnet_count"] == 1
    ifaces = result["interfaces"]
    assert len(ifaces) == 1
    assert ifaces[0]["name"] == "eth0"
    assert ifaces[0]["vlan"]["vid"] == 100
    assert ifaces[0]["vlan"]["fabric_id"] == 1
    assert ifaces[0]["linked_subnet"]["cidr"] == "10.0.0.0/24"


async def test_network_layout_partial_when_stage1_fails(monkeypatch):
    """If list_interfaces fails (Stage 1), verb returns partial=True with errors."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.get("/api/2.0/nodes/abc123/interfaces/").mock(return_value=Response(500, text="boom"))
        mock.get("/api/2.0/subnets/").mock(return_value=Response(200, json={"subnets": []}))
        async with maas_client:
            result = await NetworkLayoutTool().run(maas_client, system_id="abc123")
    assert result["partial"] is True
    assert len(result["errors"]) >= 1
    assert result["interface_count"] == 0


async def test_network_layout_empty_system_id_raises(monkeypatch):
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    async with maas_client:
        with pytest.raises(ValueError, match="system_id"):
            await NetworkLayoutTool().run(maas_client, system_id="")


async def test_network_layout_bond_child_resolution(monkeypatch):
    """Bond interface carries parents[]; tree should reflect parent->child link."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.get("/api/2.0/nodes/abc123/interfaces/").mock(
            return_value=Response(
                200,
                json={
                    "interfaces": [
                        {
                            "id": 8,
                            "name": "eth0",
                            "type": "physical",
                            "mac_address": "00:11:22:33:44:55",
                            "parents": [],
                            "ip_addresses": [],
                        },
                        {
                            "id": 9,
                            "name": "eth1",
                            "type": "physical",
                            "mac_address": "00:11:22:33:44:56",
                            "parents": [],
                            "ip_addresses": [],
                        },
                        {
                            "id": 20,
                            "name": "bond0",
                            "type": "bond",
                            "mac_address": None,
                            "parents": [8, 9],
                            "vlan_id": 100,
                            "ip_addresses": [],
                        },
                    ],
                },
            )
        )
        mock.get("/api/2.0/subnets/").mock(
            return_value=Response(
                200,
                json={
                    "subnets": [
                        {
                            "id": 5,
                            "cidr": "10.0.0.0/24",
                            "vlan": {"vid": 100, "id": 100, "fabric": "fabric-1", "fabric_id": 1},
                        }
                    ]
                },
            )
        )
        mock.get("/api/2.0/fabrics/1/vlans/100/").mock(
            return_value=Response(
                200,
                json={"id": 100, "vid": 100, "fabric": "fabric-1", "fabric_id": 1},
            )
        )
        async with maas_client:
            result = await NetworkLayoutTool().run(maas_client, system_id="abc123")
    bond = next(i for i in result["interfaces"] if i["name"] == "bond0")
    assert sorted(bond["parents"]) == [8, 9]
    assert bond["children"] == []  # no kids of the bond in this fixture


async def test_network_layout_subnet_dedup_across_interfaces(monkeypatch):
    """Two interfaces on the same subnet; subnet_count should be 1 (deduped)."""
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.get("/api/2.0/nodes/abc123/interfaces/").mock(
            return_value=Response(
                200,
                json={
                    "interfaces": [
                        {
                            "id": 8,
                            "name": "eth0",
                            "type": "physical",
                            "mac_address": None,
                            "vlan_id": 100,
                            "parents": [],
                            "ip_addresses": [],
                        },
                        {
                            "id": 9,
                            "name": "eth1",
                            "type": "physical",
                            "mac_address": None,
                            "vlan_id": 100,
                            "parents": [],
                            "ip_addresses": [],
                        },
                    ],
                },
            )
        )
        mock.get("/api/2.0/subnets/").mock(
            return_value=Response(
                200,
                json={
                    "subnets": [
                        {
                            "id": 5,
                            "cidr": "10.0.0.0/24",
                            "vlan": {"vid": 100, "id": 100, "fabric": "fabric-1", "fabric_id": 1},
                            "gateway_ip": "10.0.0.1",
                        }
                    ]
                },
            )
        )
        mock.get("/api/2.0/fabrics/1/vlans/100/").mock(
            return_value=Response(
                200,
                json={"id": 100, "vid": 100, "fabric": "fabric-1", "fabric_id": 1},
            )
        )
        async with maas_client:
            result = await NetworkLayoutTool().run(maas_client, system_id="abc123")
    assert result["subnet_count"] == 1  # deduped
    assert result["interface_count"] == 2


async def test_network_layout_by_hostname(maas_client: MaasClient) -> None:
    """Hostname path: resolve then byte-identical upstream GETs.

    Proves the hostname→system_id resolve happens and the actual upstream
    call shape is unchanged from the system_id path.
    """
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        resolve_route = mock.get(
            "/api/2.0/machines/", params={"hostname": "node-1"}
        ).mock(return_value=Response(200, json=[{"system_id": "xy7zab"}]))
        iface_route = mock.get("/api/2.0/nodes/xy7zab/interfaces/").mock(
            return_value=Response(200, json={"interfaces": []})
        )
        subnets_route = mock.get("/api/2.0/subnets/").mock(
            return_value=Response(200, json={"subnets": []})
        )
        async with maas_client:
            result = await NetworkLayoutTool().run(maas_client, hostname="node-1")
    assert resolve_route.call_count == 1
    assert iface_route.call_count == 1
    assert subnets_route.call_count == 1
    assert result["system_id"] == "xy7zab"


async def test_network_layout_real_maas_vlan_shape(monkeypatch):
    """Regression test for the fabric_id-vs-fabric field-name bug.

    Real MAAS returns the embedded ``vlan`` object with the fabric
    identifier under TWO fields:

    - ``fabric``    — string fabric name  (e.g. ``"fabric-1"``)
    - ``fabric_id`` — integer fabric id   (e.g. ``1``)

    Earlier versions of ``_internal_to_fabric_vid`` read ``fabric``
    and gated on ``isinstance(..., int)`` — the string name is never
    an int, so the function returned ``None`` for every VLAN and the
    layout counts all dropped to 0. This test pins the real shape:
    the fabric is a string name, only ``fabric_id`` carries the
    integer. If the helper regresses to reading ``fabric`` again, the
    non-zero count assertions below fail.
    """
    monkeypatch.setenv("MAASMCP_MAAS__BASE_URL", "https://maas.example.com/MAAS")
    monkeypatch.setenv("MAASMCP_MAAS__API_KEY", "k")
    monkeypatch.setenv("MAASMCP_SERVER__BEARER_TOKEN", "unit-test-token-16")
    cfg = MaasmcpConfig.load(None)
    maas_client = MaasClient(cfg.maas)
    maas_client.base_url = cfg.maas.base_url
    with respx.mock(base_url=maas_client.base_url) as mock:
        mock.get("/api/2.0/nodes/abc123/interfaces/").mock(
            return_value=Response(
                200,
                json={
                    "interfaces": [
                        {
                            "id": 8,
                            "name": "eth0",
                            "type": "physical",
                            "mac_address": "00:11:22:33:44:55",
                            "vlan_id": 5001,
                            "parents": [],
                            "ip_addresses": [],
                        },
                    ],
                },
            )
        )
        # Real MAAS: fabric is the string name, fabric_id is the int.
        mock.get("/api/2.0/subnets/").mock(
            return_value=Response(
                200,
                json={
                    "subnets": [
                        {
                            "id": 5,
                            "cidr": "10.0.0.0/24",
                            "vlan": {
                                "id": 5001,
                                "vid": 79,
                                "name": "v79",
                                "fabric": "fabric-1",
                                "fabric_id": 1,
                            },
                            "gateway_ip": "10.0.0.1",
                        }
                    ]
                },
            )
        )
        mock.get("/api/2.0/fabrics/1/vlans/79/").mock(
            return_value=Response(
                200,
                json={
                    "id": 5001,
                    "vid": 79,
                    "name": "v79",
                    "fabric": "fabric-1",
                    "fabric_id": 1,
                },
            )
        )
        async with maas_client:
            result = await NetworkLayoutTool().run(maas_client, system_id="abc123")
    # The bug: every count was 0 because the integer id was never
    # extracted from the real MAAS shape.
    assert result["fabric_count"] == 1
    assert result["vlan_count"] == 1
    assert result["subnet_count"] == 1
    assert result["interface_count"] == 1
    assert result["partial"] is False
    assert result["errors"] == []
    iface = result["interfaces"][0]
    assert iface["vlan"] is not None
    assert iface["vlan"]["vid"] == 79
    assert iface["vlan"]["fabric_id"] == 1  # not the string "fabric-1"
    assert iface["linked_subnet"]["cidr"] == "10.0.0.0/24"
