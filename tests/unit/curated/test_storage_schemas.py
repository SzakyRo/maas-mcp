"""Structural schema tests for storage curated tools.

We mock ``MaasClient`` with ``AsyncMock`` (per spec) and assert the returned
dict/list matches the declared schema shape. We do NOT exercise behavior beyond
that — the existing respx-based tests already cover runtime correctness.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from maasmcp.curated.get_block_device import GetBlockDeviceTool
from maasmcp.curated.list_raids import ListRaidsTool
from maasmcp.curated.storage_summary import StorageSummaryTool
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


async def test_storage_summary_returns_storage_summary_shape() -> None:
    client = _mock_client(
        get=[
            {
                "blockdevices": [
                    {"id": 1, "name": "sda", "size": 100000000000},
                ]
            },
            {"partitions": [{"id": 10, "size": 50000000000}]},
            {"raids": [{"id": 100, "name": "md0", "level": "raid-1"}]},
            {
                "volume_groups": [
                    {
                        "id": 200,
                        "name": "vg0",
                        "logical_volumes": [{"id": 300, "name": "lv0"}],
                    }
                ]
            },
        ]
    )

    result = await StorageSummaryTool().run(client, system_id="abc")

    assert isinstance(result, dict)
    assert result["system_id"] == "abc"
    assert result["block_devices"] == 1
    assert result["partitions"] == 1
    assert isinstance(result["total_size_gib"], float)
    assert result["raid_devices"] == 1
    assert result["volume_groups"] == 1
    assert result["logical_volumes"] == 1


async def test_get_block_device_returns_block_device_shape() -> None:
    client = _mock_client(
        get={
            "id": 1,
            "name": "sda",
            "size": 100000000000,
            "type": "physical",
            "partitions": [{"id": 10, "size": 50000000000}],
        }
    )

    result = await GetBlockDeviceTool().run(client, system_id="abc", block_device_id=1)

    assert isinstance(result, dict)
    assert result["id"] == 1
    assert result["name"] == "sda"
    assert isinstance(result["partitions"], list)
    assert len(result["partitions"]) == 1
    assert result["partitions"][0]["id"] == 10


async def test_list_raids_returns_raid_list_shape() -> None:
    client = _mock_client(
        get=[
            [
                {"id": 100, "name": "md0", "level": "raid-1"},
                {"id": 101, "name": "md1", "level": "raid-0"},
            ]
        ]
    )

    result = await ListRaidsTool().run(client, system_id="abc")

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["id"] == 100
    assert result[0]["name"] == "md0"
    assert isinstance(result[0]["level"], str)
