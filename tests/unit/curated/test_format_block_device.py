"""format_block_device: op-format with confirm gate."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from maasmcp.curated.format_block_device import FormatBlockDeviceTool
from maasmcp.maas.client import MaasClient


@pytest.mark.asyncio
async def test_confirm_false_is_noop(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="confirm=True"):
                await FormatBlockDeviceTool().run(
                    maas_client,
                    system_id="abc",
                    block_device_id=1,
                    fstype="ext4",
                    confirm=False,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_confirm_true_formats_device(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        route = mock.post("/api/2.0/nodes/abc/blockdevices/1/op-format").mock(
            return_value=Response(200, json={})
        )
        async with maas_client:
            result = await FormatBlockDeviceTool().run(
                maas_client,
                system_id="abc",
                block_device_id=1,
                fstype="ext4",
                confirm=True,
            )
    assert route.call_count == 1
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_empty_fstype_raises_value_error(maas_client: MaasClient) -> None:
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="fstype"):
                await FormatBlockDeviceTool().run(
                    maas_client,
                    system_id="abc",
                    block_device_id=1,
                    fstype="",
                    confirm=True,
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
                await FormatBlockDeviceTool().run(
                    maas_client,
                    system_id="",
                    block_device_id=1,
                    fstype="ext4",
                    confirm=True,
                )
    assert not mock.calls


@pytest.mark.asyncio
async def test_raid_fstype_rejected_before_http(maas_client: MaasClient) -> None:
    """'raid' is not a formattable fstype — MAAS marks whole-disk members on
    create_raid. Verified live 2026-08-30: op=format with fstype=raid 400s,
    so the tool must fail fast with an actionable message, never call upstream."""
    with respx.mock(base_url=maas_client.base_url) as mock:  # type: ignore[attr-defined]
        async with maas_client:
            with pytest.raises(ValueError, match="create_raid"):
                await FormatBlockDeviceTool().run(
                    maas_client,
                    system_id="abc",
                    block_device_id=1,
                    fstype="raid",
                    confirm=True,
                )
    assert not mock.calls
