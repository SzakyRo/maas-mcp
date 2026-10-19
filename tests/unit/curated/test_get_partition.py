"""get_partition: GET one partition."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.get_partition import GetPartitionTool
from maasmcp.maas.client import MaasClient
from maasmcp.maas.errors import MCPUpstreamError


@pytest.mark.asyncio
async def test_get_partition_returns_dict(maas_client: MaasClient) -> None:
    part = {"id": 3, "size": 500000, "filesystem": None}
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.get("/api/2.0/nodes/abc/blockdevices/7/partitions/3").mock(
            return_value=Response(200, json=part)
        )
        async with maas_client:
            result = await GetPartitionTool().run(
                maas_client, system_id="abc", block_device_id=7, partition_id=3
            )
    assert route.call_count == 1
    assert result == part


@pytest.mark.asyncio
async def test_get_partition_404_surfaces_as_upstream_error(
    maas_client: MaasClient,
) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        mock.get("/api/2.0/nodes/abc/blockdevices/7/partitions/99").mock(
            return_value=Response(404, text="missing")
        )
        async with maas_client:
            with pytest.raises(MCPUpstreamError) as exc_info:
                await GetPartitionTool().run(
                    maas_client, system_id="abc", block_device_id=7, partition_id=99
                )
    assert "404" in str(exc_info.value)


@pytest.mark.asyncio
async def test_partition_id_zero_raises_value_error(
    maas_client: MaasClient,
) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="partition_id"):
                await GetPartitionTool().run(
                    maas_client, system_id="abc", block_device_id=7, partition_id=0
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_empty_system_id_raises_value_error(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="system_id"):
                await GetPartitionTool().run(
                    maas_client,
                    system_id="",
                    block_device_id=1,
                    partition_id=1,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_block_device_id_zero_raises_value_error(
    maas_client: MaasClient,
) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="block_device_id"):
                await GetPartitionTool().run(
                    maas_client,
                    system_id="abc",
                    block_device_id=0,
                    partition_id=1,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_get_partition_non_dict_response_raises(
    maas_client: MaasClient,
) -> None:
    """Schema drift: MAAS 200 with a non-dict body should not silently return {}."""
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.get("/api/2.0/nodes/abc/blockdevices/7/partitions/3").mock(
            return_value=Response(200, json=[{"unexpected": "list"}])
        )
        async with maas_client:
            with pytest.raises(ValueError, match="non-dict"):
                await GetPartitionTool().run(
                    maas_client,
                    system_id="abc",
                    block_device_id=7,
                    partition_id=3,
                )
    assert route.call_count == 1
