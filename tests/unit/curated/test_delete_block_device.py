"""delete_block_device: DELETE with confirm gate."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.delete_block_device import DeleteBlockDeviceTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_confirm_false_is_noop(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await DeleteBlockDeviceTool().run(
                    maas_client, system_id="abc", block_device_id=1, confirm=False
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_confirm_true_deletes_device(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.delete("/api/2.0/nodes/abc/blockdevices/1/").mock(return_value=Response(204))
        async with maas_client:
            result = await DeleteBlockDeviceTool().run(
                maas_client, system_id="abc", block_device_id=1, confirm=True
            )
    assert route.call_count == 1
    assert result["status"] == "ok"
    assert result["operation"] == "delete"
    assert result["resource_id"] == 1


@pytest.mark.asyncio
async def test_block_device_id_zero_raises_value_error(
    maas_client: MaasClient,
) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="block_device_id"):
                await DeleteBlockDeviceTool().run(
                    maas_client, system_id="abc", block_device_id=0, confirm=True
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_empty_system_id_with_confirm_true_still_fails(
    maas_client: MaasClient,
) -> None:
    """Path validation must happen BEFORE the confirm check."""
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="system_id"):
                await DeleteBlockDeviceTool().run(
                    maas_client,
                    system_id="",
                    block_device_id=1,
                    confirm=True,
                )
    assert not mock.calls
