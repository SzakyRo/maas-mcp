"""Structural schema tests for network curated tools.

We mock ``MaasClient`` with ``AsyncMock`` (per spec) and assert the
returned dict/list matches the declared schema shape. We do NOT exercise
behavior beyond that — the existing respx-based tests already cover runtime
correctness.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from maasmcp.curated.create_bond import CreateBondTool
from maasmcp.curated.get_interface import GetInterfaceTool
from maasmcp.curated.get_subnet import GetSubnetTool
from maasmcp.curated.ip_address_reserve import IpAddressReserveTool
from maasmcp.curated.link_subnet import LinkSubnetTool
from maasmcp.curated.list_interfaces import ListInterfacesTool
from maasmcp.curated.list_subnets import ListSubnetsTool
from maasmcp.curated.network_layout import NetworkLayoutTool
from maasmcp.maas.client import MaasClient

pytestmark = pytest.mark.asyncio


def _mock_client(**method_returns: Any) -> MaasClient:
    """Build an AsyncMock(spec=MaasClient) with per-method return_values."""
    client = AsyncMock(spec=MaasClient)
    for name, value in method_returns.items():
        mock_method = getattr(client, name)
        if isinstance(value, list):
            mock_method.side_effect = value
        else:
            mock_method.return_value = value
    return client


async def test_network_layout_returns_network_layout_shape() -> None:
    client = _mock_client(
        get=[
            {
                "interfaces": [
                    {
                        "id": 8,
                        "name": "eth0",
                        "type": "physical",
                        "mac_address": "00:11:22:33:44:55",
                        "vlan_id": 100,
                        "parents": [],
                        "ip_addresses": [],
                    }
                ]
            },
            {
                "subnets": [
                    {
                        "id": 5,
                        "cidr": "10.0.0.0/24",
                        "gateway_ip": "10.0.0.1",
                        "vlan": {
                            "id": 100,
                            "vid": 100,
                            "fabric": "fabric-1",
                            "fabric_id": 1,
                        },
                    }
                ]
            },
            {
                "id": 100,
                "vid": 100,
                "name": "v100",
                "fabric": "fabric-1",
                "fabric_id": 1,
            },
            {"vlans": [{"id": 100, "vid": 100}]},
        ]
    )

    result = await NetworkLayoutTool().run(client, system_id="abc")

    assert isinstance(result, dict)
    assert result["system_id"] == "abc"
    assert result["fabric_count"] == 1
    assert result["vlan_count"] == 1
    assert result["subnet_count"] == 1
    assert result["interface_count"] == 1
    assert result["ip_range_count"] == 0
    assert result["partial"] is False
    assert result["errors"] == []
    assert isinstance(result["interfaces"], list)
    assert len(result["interfaces"]) == 1
    iface = result["interfaces"][0]
    assert isinstance(iface["vlan"], dict)
    assert iface["vlan"]["fabric_id"] == 1
    assert isinstance(iface["linked_subnet"], dict)
    assert iface["linked_subnet"]["cidr"] == "10.0.0.0/24"
    assert isinstance(result["fabric_vlan_counts"], dict)


async def test_get_subnet_returns_subnet_shape() -> None:
    client = _mock_client(
        get={
            "id": 3,
            "cidr": "10.0.0.0/24",
            "gateway_ip": "10.0.0.1",
            "vlan": {"id": 100, "vid": 100, "fabric_id": 1},
        }
    )

    result = await GetSubnetTool().run(client, subnet_id=3)

    assert isinstance(result, dict)
    assert result["id"] == 3
    assert result["cidr"] == "10.0.0.0/24"
    assert isinstance(result["vlan"], dict)
    assert result["vlan"]["vid"] == 100


async def test_list_interfaces_returns_interface_list_shape() -> None:
    client = _mock_client(
        get={
            "interfaces": [
                {
                    "id": 8,
                    "name": "eth0",
                    "type": "physical",
                    "mac_address": "00:11:22:33:44:55",
                }
            ]
        }
    )

    result = await ListInterfacesTool().run(client, system_id="abc")

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["id"] == 8
    assert result[0]["type"] == "physical"
    assert result[0]["mac_address"] == "00:11:22:33:44:55"


async def test_list_subnets_returns_subnet_list_shape() -> None:
    client = _mock_client(
        get={
            "subnets": [
                {"id": 1, "cidr": "10.0.0.0/24"},
                {"id": 2, "cidr": "10.0.1.0/24"},
            ]
        }
    )

    result = await ListSubnetsTool().run(client)

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["id"] == 1
    assert isinstance(result[0]["cidr"], str)


async def test_get_interface_returns_interface_shape() -> None:
    client = _mock_client(
        get={
            "id": 8,
            "name": "eth0",
            "type": "physical",
            "mac_address": "00:11:22:33:44:55",
            "vlan_id": 100,
        }
    )

    result = await GetInterfaceTool().run(client, system_id="abc", iface_id=8)

    assert isinstance(result, dict)
    assert result["id"] == 8
    assert result["type"] == "physical"
    assert isinstance(result["mac_address"], str)


async def test_link_subnet_returns_interface_shape() -> None:
    client = _mock_client(post={"id": 8, "links": [{"id": 1, "subnet_id": 5}]})

    result = await LinkSubnetTool().run(
        client,
        system_id="abc",
        iface_id=8,
        subnet_id=5,
        mode="AUTO",
        confirm=True,
    )

    assert isinstance(result, dict)
    assert result["id"] == 8
    assert isinstance(result["links"], list)


async def test_create_bond_returns_bond_shape_with_link_states() -> None:
    client = _mock_client(
        put={},
        post={
            "id": 20,
            "type": "bond",
            "parents": [8, 9],
            "name": "bond0",
        },
        get=[
            {"id": 20, "link_connected": True, "type": "bond"},
            {"id": 8, "name": "eth0", "link_connected": False},
            {"id": 9, "name": "eth1", "link_connected": False},
        ],
    )

    result = await CreateBondTool().run(
        client,
        system_id="abc",
        name="bond0",
        members=[8, 9],
        confirm=True,
    )

    assert isinstance(result, dict)
    assert result["id"] == 20
    assert result["type"] == "bond"
    assert isinstance(result.get("link_state_classification"), str)
    assert isinstance(result.get("member_link_states"), list)
    assert len(result["member_link_states"]) == 2


async def test_ip_address_reserve_returns_ipaddress_shape() -> None:
    client = _mock_client(
        post={
            "ip": "10.0.0.5",
            "subnet": 3,
            "type": "User reserved",
        }
    )

    result = await IpAddressReserveTool().run(
        client,
        subnet="10.0.0.0/24",
        confirm=True,
    )

    assert isinstance(result, dict)
    assert result["ip"] == "10.0.0.5"
    assert isinstance(result["subnet"], int)
