"""update_block_device: PUT with confirm gate."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.update_block_device import UpdateBlockDeviceTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_confirm_false_is_noop(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await UpdateBlockDeviceTool().run(
                    maas_client,
                    system_id="abc",
                    block_device_id=1,
                    name="sdb",
                    confirm=False,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_confirm_true_updates_device(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.put("/api/2.0/nodes/abc/blockdevices/1/").mock(return_value=Response(204))
        async with maas_client:
            result = await UpdateBlockDeviceTool().run(
                maas_client,
                system_id="abc",
                block_device_id=1,
                name="sdb",
                confirm=True,
            )
    assert route.call_count == 1
    assert result == {
        "status": "ok",
        "system_id": "abc",
        "resource_id": 1,
        "operation": "update",
    }


@pytest.mark.asyncio
async def test_empty_system_id_with_confirm_true_still_fails(
    maas_client: MaasClient,
) -> None:
    """Path validation must happen BEFORE the confirm check."""
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="system_id"):
                await UpdateBlockDeviceTool().run(
                    maas_client,
                    system_id="",
                    block_device_id=1,
                    name="sda",
                    confirm=True,
                )
    assert not mock.calls
