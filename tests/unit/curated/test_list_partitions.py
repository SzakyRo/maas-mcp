"""list_partitions: GET partitions on a block device."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.list_partitions import ListPartitionsTool
from maasmcp.maas.client import MaasClient
from maasmcp.maas.errors import MCPUpstreamError


@pytest.mark.asyncio
async def test_list_partitions_returns_list(maas_client: MaasClient) -> None:
    parts = [{"id": 1, "size": 500000}, {"id": 2, "size": 500000}]
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.get("/api/2.0/nodes/abc/blockdevices/7/partitions/").mock(
            return_value=Response(200, json=parts)
        )
        async with maas_client:
            result = await ListPartitionsTool().run(maas_client, system_id="abc", block_device_id=7)
    assert route.call_count == 1
    assert result == parts


@pytest.mark.asyncio
async def test_list_partitions_handles_envelope(maas_client: MaasClient) -> None:
    parts = [{"id": 1}]
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        mock.get("/api/2.0/nodes/abc/blockdevices/7/partitions/").mock(
            return_value=Response(200, json={"partitions": parts})
        )
        async with maas_client:
            result = await ListPartitionsTool().run(maas_client, system_id="abc", block_device_id=7)
    assert result == parts


@pytest.mark.asyncio
async def test_no_partition_table_500_falls_back_to_block_device(
    maas_client: MaasClient,
) -> None:
    """MAAS 500s on devices with no PartitionTable row; use inline partitions."""
    parts = [{"id": 9, "size": 1000}]
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        mock.get("/api/2.0/nodes/abc/blockdevices/7/partitions/").mock(
            return_value=Response(
                500,
                text="PartitionTable matching query does not exist.",
                headers={"content-type": "text/plain"},
            )
        )
        device_route = mock.get("/api/2.0/nodes/abc/blockdevices/7/").mock(
            return_value=Response(200, json={"id": 7, "partitions": parts})
        )
        async with maas_client:
            result = await ListPartitionsTool().run(maas_client, system_id="abc", block_device_id=7)
    assert device_route.call_count == 1
    assert result == parts


@pytest.mark.asyncio
async def test_no_partition_table_500_empty_inline_partitions(
    maas_client: MaasClient,
) -> None:
    """A fresh, unused disk falls back to an empty list rather than an error."""
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        mock.get("/api/2.0/nodes/abc/blockdevices/7/partitions/").mock(
            return_value=Response(
                500,
                text="PartitionTable matching query does not exist.",
                headers={"content-type": "text/plain"},
            )
        )
        mock.get("/api/2.0/nodes/abc/blockdevices/7/").mock(
            return_value=Response(
                200, json={"id": 7, "partition_table_type": None, "partitions": []}
            )
        )
        async with maas_client:
            result = await ListPartitionsTool().run(maas_client, system_id="abc", block_device_id=7)
    assert result == []


@pytest.mark.asyncio
async def test_unrelated_500_still_raises(maas_client: MaasClient) -> None:
    """Only the missing-PartitionTable 500 is tolerated; other 500s propagate."""
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        mock.get("/api/2.0/nodes/abc/blockdevices/7/partitions/").mock(
            return_value=Response(500, text="Database is down")
        )
        async with maas_client:
            with pytest.raises(MCPUpstreamError):
                await ListPartitionsTool().run(maas_client, system_id="abc", block_device_id=7)


@pytest.mark.asyncio
async def test_bad_block_device_id_raises_value_error(
    maas_client: MaasClient,
) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="block_device_id"):
                await ListPartitionsTool().run(maas_client, system_id="abc", block_device_id=0)
    assert not mock.calls


@pytest.mark.asyncio
async def test_empty_system_id_raises_value_error(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="system_id"):
                await ListPartitionsTool().run(maas_client, system_id="", block_device_id=1)
    assert not mock.calls
