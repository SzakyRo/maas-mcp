"""create_partition: POST partitions with confirm gate."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.create_partition import CreatePartitionTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_confirm_false_is_noop(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await CreatePartitionTool().run(
                    maas_client,
                    system_id="abc",
                    block_device_id=1,
                    size="1000000",
                    confirm=False,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_confirm_true_creates_partition(maas_client: MaasClient) -> None:
    part = {"id": 5, "size": 1000000, "device_id": 1}
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.post("/api/2.0/nodes/abc/blockdevices/1/partitions/").mock(
            return_value=Response(200, json=part)
        )
        async with maas_client:
            result = await CreatePartitionTool().run(
                maas_client,
                system_id="abc",
                block_device_id=1,
                size="1000000",
                confirm=True,
            )
    assert route.call_count == 1
    assert result == part


@pytest.mark.asyncio
async def test_empty_system_id_with_confirm_true_still_fails(
    maas_client: MaasClient,
) -> None:
    """Path validation must happen BEFORE the confirm check."""
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="system_id"):
                await CreatePartitionTool().run(
                    maas_client,
                    system_id="",
                    block_device_id=1,
                    size="1000000",
                    confirm=True,
                )
    assert not mock.calls
