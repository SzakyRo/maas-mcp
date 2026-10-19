"""Schema-shape tests for machine lifecycle curated tools.

These tests verify that the normalized read tools return dicts matching their
``TypedDict`` return annotations. Runtime behavior is mocked with
``AsyncMock`` so no MAAS instance is required.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from maasmcp.curated.find_available_machines import FindAvailableMachinesTool
from maasmcp.curated.get_machine import GetMachineTool
from maasmcp.curated.list_machines import ListMachinesTool
from maasmcp.curated.power_status import PowerStatusTool
from maasmcp.curated.summary import SummaryTool
from maasmcp.curated.wait_for_state import WaitForStateTool

if TYPE_CHECKING:
    from maasmcp.curated._schemas.base import FleetSummary, MachineNormalized, MachineSlim
    from maasmcp.curated._schemas.machines import MachineRecord


@pytest.fixture
def client() -> AsyncMock:
    return AsyncMock()


@pytest.mark.asyncio
async def test_get_machine_returns_machine_normalized(client: AsyncMock) -> None:
    client.get.return_value = {
        "system_id": "abc123",
        "hostname": "node-1",
        "tag_names": ["fast"],
        "pool": {"name": "default"},
        "owner": {"username": "admin"},
        "power_state": "off",
        "osystem": "ubuntu",
        "distro_series": "jammy",
        "last_commissioned": None,
        "boot_disk": {"id": 1, "name": "sda"},
    }
    result = await GetMachineTool().run(client, identifier="abc123")
    assert result["system_id"] == "abc123"
    assert result["hostname"] == "node-1"
    assert result["pool"] == "default"
    assert result["owner"] == "admin"
    assert result["os"] == "ubuntu jammy"
    _: MachineNormalized = result


@pytest.mark.asyncio
async def test_list_machines_returns_machine_slim_list(client: AsyncMock) -> None:
    client.paginated_get.return_value = [
        {
            "system_id": "a",
            "hostname": "node-a",
            "status_name": "Ready",
            "power_state": "off",
            "tag_names": ["fast"],
            "pool": {"name": "default"},
        },
        {
            "system_id": "b",
            "hostname": "node-b",
            "status_name": "Deployed",
            "power_state": "on",
            "tag_names": [],
            "pool": {"name": "gpu"},
        },
    ]
    result = await ListMachinesTool().run(client)
    assert len(result) == 2
    assert result[0]["system_id"] == "a"
    assert result[1]["pool"] == "gpu"
    _: list[MachineSlim] = result


@pytest.mark.asyncio
async def test_find_available_machines_returns_machine_slim_list(client: AsyncMock) -> None:
    client.paginated_get.return_value = [
        {
            "system_id": "a",
            "hostname": "node-a",
            "status_name": "Ready",
            "power_state": "off",
            "tag_names": ["fast"],
            "pool": {"name": "default"},
        },
        {
            "system_id": "b",
            "hostname": "node-b",
            "status_name": "Deployed",
            "power_state": "on",
            "tag_names": [],
            "pool": {"name": "gpu"},
        },
    ]
    result = await FindAvailableMachinesTool().run(client)
    assert len(result) == 1
    assert result[0]["system_id"] == "a"
    _: list[MachineSlim] = result


@pytest.mark.asyncio
async def test_summary_returns_fleet_summary(client: AsyncMock) -> None:
    client.paginated_get.side_effect = [
        [
            {
                "status_name": "Ready",
                "pool": {"name": "p1"},
                "zone": {"name": "z1"},
                "memory": 1024,
                "cpu_count": 4,
            },
            {
                "status_name": "Deployed",
                "pool": {"name": "p1"},
                "zone": {"name": "z2"},
                "memory": 1024,
                "cpu_count": 4,
            },
        ],
        [
            {"id": 1, "status_name": "Ready"},
            {"id": 2, "status_name": "Ready"},
            {"id": 3, "status_name": "Broken"},
        ],
    ]
    result = await SummaryTool().run(client)
    assert result["machine_count"] == 2
    assert result["pod_count"] == 3
    assert result["total_memory_mb"] == 2048
    assert result["total_cpu_count"] == 8
    assert result["by_status"] == {"Ready": 1, "Deployed": 1}
    assert result["by_pool"] == {"p1": 2}
    assert result["by_zone"] == {"z1": 1, "z2": 1}
    assert result["pod_count_by_status"] == {"Ready": 2, "Broken": 1}
    _: FleetSummary = result


@pytest.mark.asyncio
async def test_power_status_returns_string(client: AsyncMock) -> None:
    client.get.return_value = {"power_state": "on"}
    result = await PowerStatusTool().run(client, system_id="abc")
    assert result == "on"


@pytest.mark.asyncio
async def test_wait_for_state_returns_machine_record(client: AsyncMock) -> None:
    client.get.return_value = {
        "system_id": "abc",
        "hostname": "node-1",
        "status_name": "Deployed",
        "power_state": "on",
    }
    result = await WaitForStateTool().run(
        client,
        system_id="abc",
        target_states=["Deployed"],
        timeout_seconds=1,
        poll_interval_seconds=0.1,
    )
    assert result["status_name"] == "Deployed"
    _: MachineRecord = result
